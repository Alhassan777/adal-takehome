"""DependEval Task 1 (Dependency Recognition) benchmark adapter.

Evaluates the agent's ability to determine the correct dependency ordering
of files within a repository using its structural tools (import graph,
trace_module, get_imports).

Expected output: JSON array of filenames in dependency order
(leaf dependencies first, dependents last).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .configs import AblationConfig
from .runner import RunResult, run_agent, init_session_for_config

logger = logging.getLogger(__name__)

VENDOR_DIR = Path(__file__).parent / "vendor"
DEPENDEVAL_DIR = VENDOR_DIR / "DependEval"
DEPENDEVAL_REPO_URL = "https://github.com/ink7-sudo/DependEval.git"

DEPENDEVAL_PROMPT = """\
Analyze the dependency relationships between the Python files in this repository.
Determine the correct order in which files depend on each other.

Output ONLY a JSON array of filenames in dependency order, where dependencies \
come first and files that depend on them come later.

Example format: ["utils.py", "models.py", "services.py", "main.py"]

Output the JSON array and nothing else."""


@dataclass
class DependEvalTask:
    """A single DependEval Dependency Recognition task."""

    task_id: str
    language: str
    files: dict[str, str]  # filename -> file content
    ground_truth: list[str]  # expected ordering


@dataclass
class DependEvalResult:
    """Result of a single DependEval evaluation."""

    task: DependEvalTask
    run_result: RunResult
    predicted_order: list[str]
    exact_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task.task_id,
            "language": self.task.language,
            "files": list(self.task.files.keys()),
            "ground_truth": self.task.ground_truth,
            "predicted_order": self.predicted_order,
            "exact_match": self.exact_match,
            "duration_s": self.run_result.duration_s,
            "config_id": self.run_result.config_id,
            "success": self.run_result.success,
            "error": self.run_result.error,
        }


def setup_dependeval() -> bool:
    """Clone DependEval if not present."""
    if DEPENDEVAL_DIR.exists() and (DEPENDEVAL_DIR / ".git").exists():
        logger.info("DependEval already cloned")
        return True

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Cloning DependEval -> {DEPENDEVAL_DIR}")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", DEPENDEVAL_REPO_URL, str(DEPENDEVAL_DIR)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone DependEval: {e.stderr.decode()}")
        return False


def load_dataset(language: str = "python") -> list[DependEvalTask]:
    """Load the DependEval Dependency Recognition dataset for Python."""
    tasks = []

    data_dirs = [
        DEPENDEVAL_DIR / "data" / "DR" / language,
        DEPENDEVAL_DIR / "data" / "dependency_recognition" / language,
        DEPENDEVAL_DIR / "dataset" / "DR" / language,
        DEPENDEVAL_DIR / "DR" / language,
    ]

    dataset_dir = None
    for d in data_dirs:
        if d.exists():
            dataset_dir = d
            break

    if dataset_dir is None:
        for jsonl_path in DEPENDEVAL_DIR.rglob("*.jsonl"):
            if "DR" in str(jsonl_path) or "dependency" in str(jsonl_path).lower():
                tasks.extend(_load_from_jsonl(jsonl_path, language))
                break

        if not tasks:
            for json_path in DEPENDEVAL_DIR.rglob("*.json"):
                if "DR" in str(json_path) or "dependency" in str(json_path).lower():
                    tasks.extend(_load_from_json(json_path, language))
                    break

        if not tasks:
            logger.warning("Could not find DependEval DR dataset, scanning all data files")
            for f in DEPENDEVAL_DIR.rglob("*"):
                if f.suffix in (".json", ".jsonl") and f.stat().st_size > 100:
                    if f.suffix == ".jsonl":
                        found = _load_from_jsonl(f, language)
                    else:
                        found = _load_from_json(f, language)
                    if found:
                        tasks.extend(found)
                        logger.info(f"Found {len(found)} tasks in {f}")
                        break

    else:
        for item_path in sorted(dataset_dir.iterdir()):
            if item_path.suffix == ".json":
                tasks.extend(_load_from_json(item_path, language))
            elif item_path.suffix == ".jsonl":
                tasks.extend(_load_from_jsonl(item_path, language))
            elif item_path.is_dir():
                task = _load_from_directory(item_path, language)
                if task:
                    tasks.append(task)

    logger.info(f"Loaded {len(tasks)} DependEval DR tasks for {language}")
    return tasks


def _load_from_jsonl(path: Path, language: str) -> list[DependEvalTask]:
    """Load tasks from a JSONL file."""
    tasks = []
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                task = _parse_task_data(data, f"{path.stem}_{i}", language)
                if task:
                    tasks.append(task)
            except json.JSONDecodeError:
                continue
    return tasks


def _load_from_json(path: Path, language: str) -> list[DependEvalTask]:
    """Load tasks from a JSON file (single object or array)."""
    tasks = []
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        for i, item in enumerate(data):
            task = _parse_task_data(item, f"{path.stem}_{i}", language)
            if task:
                tasks.append(task)
    elif isinstance(data, dict):
        task = _parse_task_data(data, path.stem, language)
        if task:
            tasks.append(task)

    return tasks


def _parse_task_data(data: dict, task_id: str, target_language: str) -> DependEvalTask | None:
    """Parse a single task from raw dict data."""
    lang = data.get("language", data.get("lang", "")).lower()
    if lang and lang != target_language.lower():
        return None

    files = data.get("files", data.get("code", data.get("snippets", {})))
    if isinstance(files, str):
        return None

    ground_truth = data.get("ground_truth", data.get("answer", data.get("order", data.get("dependency_order", []))))

    if isinstance(ground_truth, str):
        try:
            ground_truth = json.loads(ground_truth)
        except json.JSONDecodeError:
            ground_truth = [s.strip().strip('"').strip("'") for s in ground_truth.strip("[]").split(",")]

    if not files or not ground_truth:
        return None

    return DependEvalTask(
        task_id=task_id,
        language=target_language,
        files=files,
        ground_truth=ground_truth,
    )


def _load_from_directory(dir_path: Path, language: str) -> DependEvalTask | None:
    """Load a task from a directory containing code files + metadata."""
    meta_path = dir_path / "meta.json"
    if not meta_path.exists():
        meta_path = dir_path / "metadata.json"
    if not meta_path.exists():
        return None

    with open(meta_path) as f:
        meta = json.load(f)

    ground_truth = meta.get("ground_truth", meta.get("order", []))
    if not ground_truth:
        return None

    ext = ".py" if language == "python" else f".{language}"
    files = {}
    for code_file in dir_path.iterdir():
        if code_file.suffix == ext:
            files[code_file.name] = code_file.read_text()

    if not files:
        return None

    return DependEvalTask(
        task_id=dir_path.name,
        language=language,
        files=files,
        ground_truth=ground_truth,
    )


def create_temp_repo(task: DependEvalTask) -> Path:
    """Create a temporary directory with the task's files for indexing."""
    temp_dir = Path(tempfile.mkdtemp(prefix=f"dependeval_{task.task_id}_"))

    for filename, content in task.files.items():
        file_path = temp_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return temp_dir


def parse_predicted_order(answer: str) -> list[str]:
    """Extract the predicted file ordering from agent response."""
    import re

    json_match = re.search(r'\[.*?\]', answer, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                return parsed
        except json.JSONDecodeError:
            pass

    lines = answer.strip().split("\n")
    file_pattern = re.compile(r'[\w/]+\.py')
    files = []
    for line in lines:
        matches = file_pattern.findall(line)
        for m in matches:
            if m not in files:
                files.append(m)

    return files


def evaluate_task(
    task: DependEvalTask,
    config: AblationConfig,
    *,
    verbose: bool = False,
) -> DependEvalResult:
    """Evaluate a single DependEval DR task."""
    temp_repo = create_temp_repo(task)

    try:
        run_result = run_agent(str(temp_repo), DEPENDEVAL_PROMPT, config, verbose=verbose)
        predicted = parse_predicted_order(run_result.answer) if run_result.success else []

        predicted_normalized = [Path(f).name for f in predicted]
        ground_truth_normalized = [Path(f).name for f in task.ground_truth]

        exact_match = predicted_normalized == ground_truth_normalized

        return DependEvalResult(
            task=task,
            run_result=run_result,
            predicted_order=predicted,
            exact_match=exact_match,
        )
    finally:
        shutil.rmtree(temp_repo, ignore_errors=True)


def run_dependeval_evaluation(
    config: AblationConfig,
    *,
    language: str = "python",
    max_tasks: int | None = None,
    progress_callback=None,
    verbose: bool = False,
) -> list[DependEvalResult]:
    """Run the full DependEval DR evaluation for a given config."""
    if not setup_dependeval():
        logger.error("Failed to set up DependEval")
        return []

    tasks = load_dataset(language)
    if max_tasks:
        tasks = tasks[:max_tasks]

    if not tasks:
        logger.error("No DependEval tasks loaded")
        return []

    results = []
    for i, task in enumerate(tasks):
        logger.info(f"[{i+1}/{len(tasks)}] Task {task.task_id} ({len(task.files)} files)")
        result = evaluate_task(task, config, verbose=verbose)
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(tasks), result)

    return results


def compute_metrics(results: list[DependEvalResult]) -> dict[str, Any]:
    """Compute aggregate metrics from DependEval results."""
    total = len(results)
    if total == 0:
        return {"exact_match_rate": 0.0, "total": 0, "matched": 0, "errors": 0}

    matched = sum(1 for r in results if r.exact_match)
    errors = sum(1 for r in results if not r.run_result.success)
    avg_duration = sum(r.run_result.duration_s for r in results) / total

    partial_matches = 0
    for r in results:
        if not r.exact_match and r.predicted_order:
            pred_set = set(Path(f).name for f in r.predicted_order)
            truth_set = set(Path(f).name for f in r.task.ground_truth)
            if pred_set == truth_set:
                partial_matches += 1

    return {
        "exact_match_rate": matched / total,
        "total": total,
        "matched": matched,
        "errors": errors,
        "partial_matches": partial_matches,
        "avg_duration_s": round(avg_duration, 2),
    }
