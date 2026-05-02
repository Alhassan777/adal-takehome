"""RepoQA benchmark adapter.

Evaluates the agent's ability to locate a specific function in a repository
given only a natural-language description (Search Needle Function task).

Two tracks:
  Track A (standard): Uses RepoQA's concatenated context approach for
    comparison with published baselines.
  Track B (navigation): Clones actual repos and lets the agent navigate
    with its full tool suite — the real test of our system.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .configs import AblationConfig
from .runner import RunResult, run_agent, init_session_for_config

logger = logging.getLogger(__name__)

REPOQA_PROMPT_TEMPLATE = """\
Find the function described below and return its exact source code in a \
markdown code block (```python ... ```). Return ONLY the function, nothing else.

Function Description:
{description}"""

DATASET_CACHE_DIR = Path(__file__).parent / "vendor" / "repoqa_data"
REPOS_DIR = Path(__file__).parent / "vendor" / "repoqa_repos"


@dataclass
class RepoQATask:
    """A single RepoQA Search Needle Function task."""

    repo: str
    function_name: str
    language: str
    file_path: str
    description: str
    code_context: str
    position_ratio: float = 0.0


@dataclass
class RepoQAResult:
    """Result of a single RepoQA evaluation."""

    task: RepoQATask
    run_result: RunResult
    extracted_code: str
    bleu_score: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.task.repo,
            "function_name": self.task.function_name,
            "file_path": self.task.file_path,
            "description": self.task.description[:200],
            "extracted_code": self.extracted_code[:500],
            "bleu_score": self.bleu_score,
            "passed": self.passed,
            "duration_s": self.run_result.duration_s,
            "config_id": self.run_result.config_id,
            "success": self.run_result.success,
            "error": self.run_result.error,
        }


def load_dataset(language: str = "python") -> list[RepoQATask]:
    """Load the RepoQA dataset for a given language.

    Attempts to use the repoqa package first, falls back to HuggingFace datasets.
    """
    tasks = []

    try:
        from repoqa.data import get_dataset
        dataset = get_dataset()
    except (ImportError, Exception):
        try:
            from datasets import load_dataset as hf_load
            dataset = hf_load("evalplus/repoqa", split="test")
        except (ImportError, Exception):
            dataset_path = DATASET_CACHE_DIR / f"{language}.jsonl"
            if not dataset_path.exists():
                raise FileNotFoundError(
                    f"RepoQA dataset not found. Install with: pip install repoqa\n"
                    f"Or place dataset at: {dataset_path}"
                )
            with open(dataset_path) as f:
                dataset = [json.loads(line) for line in f]

    for item in dataset:
        if isinstance(item, dict):
            lang = item.get("language", "")
            if lang.lower() != language.lower():
                continue
            tasks.append(RepoQATask(
                repo=item.get("repo", ""),
                function_name=item.get("name", ""),
                language=lang,
                file_path=item.get("path", ""),
                description=item.get("description", ""),
                code_context=item.get("code_context", ""),
                position_ratio=item.get("position_ratio", 0.0),
            ))

    logger.info(f"Loaded {len(tasks)} RepoQA tasks for {language}")
    return tasks


def clone_repo(repo_slug: str, target_dir: Path) -> Path:
    """Clone a GitHub repo if not already present."""
    repo_dir = target_dir / repo_slug.replace("/", "_")
    if repo_dir.exists() and (repo_dir / ".git").exists():
        logger.info(f"Repo already cloned: {repo_slug}")
        return repo_dir

    repo_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo_slug}.git"
    logger.info(f"Cloning {url} -> {repo_dir}")

    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(repo_dir)],
        check=True,
        capture_output=True,
    )
    return repo_dir


def extract_code_block(text: str) -> str:
    """Extract the first markdown code block from agent output."""
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    lines = text.strip().split("\n")
    code_lines = []
    in_def = False
    for line in lines:
        if line.strip().startswith("def ") or line.strip().startswith("async def "):
            in_def = True
        if in_def:
            code_lines.append(line)

    return "\n".join(code_lines).strip() if code_lines else text.strip()


def compute_bleu_score(candidate: str, reference: str) -> float:
    """Compute BLEU-4 similarity between candidate and reference code."""
    if not candidate or not reference:
        return 0.0

    def get_ngrams(tokens: list[str], n: int) -> dict[tuple, int]:
        ngrams: dict[tuple, int] = {}
        for i in range(len(tokens) - n + 1):
            gram = tuple(tokens[i:i + n])
            ngrams[gram] = ngrams.get(gram, 0) + 1
        return ngrams

    cand_tokens = candidate.split()
    ref_tokens = reference.split()

    if not cand_tokens or not ref_tokens:
        return 0.0

    brevity_penalty = min(1.0, len(cand_tokens) / max(len(ref_tokens), 1))

    import math

    log_score = 0.0
    has_nonzero_precision = False
    for n in range(1, 5):
        cand_ngrams = get_ngrams(cand_tokens, n)
        ref_ngrams = get_ngrams(ref_tokens, n)

        matches = 0
        total = 0
        for gram, count in cand_ngrams.items():
            total += count
            if gram in ref_ngrams:
                matches += min(count, ref_ngrams[gram])

        if total == 0:
            continue
        precision = matches / total
        if precision > 0:
            has_nonzero_precision = True
            log_score += math.log(precision) / 4.0
        else:
            return 0.0

    if not has_nonzero_precision:
        return 0.0
    return brevity_penalty * math.exp(log_score)


def evaluate_task_navigation(
    task: RepoQATask,
    config: AblationConfig,
    repos_dir: Path,
    *,
    verbose: bool = False,
) -> RepoQAResult:
    """Evaluate a single RepoQA task using navigation mode (Track B)."""
    repo_dir = repos_dir / task.repo.replace("/", "_")
    if not repo_dir.exists():
        repo_dir = clone_repo(task.repo, repos_dir)

    question = REPOQA_PROMPT_TEMPLATE.format(description=task.description)

    run_result = run_agent(str(repo_dir), question, config, verbose=verbose)
    extracted = extract_code_block(run_result.answer) if run_result.success else ""

    ground_truth = _extract_ground_truth(task)
    bleu = compute_bleu_score(extracted, ground_truth)
    passed = bleu >= 0.8

    return RepoQAResult(
        task=task,
        run_result=run_result,
        extracted_code=extracted,
        bleu_score=bleu,
        passed=passed,
    )


def _extract_ground_truth(task: RepoQATask) -> str:
    """Extract the ground-truth needle function from the code context.

    Uses the function name and file path to locate it within the context.
    """
    context = task.code_context
    if not context:
        return ""

    patterns = [
        rf"((?:async\s+)?def\s+{re.escape(task.function_name)}\s*\(.*?\n(?:(?!\ndef\s).*\n)*)",
        rf"(def\s+{re.escape(task.function_name)}.*?)(?=\ndef\s|\nclass\s|\Z)",
    ]

    for pattern in patterns:
        match = re.search(pattern, context, re.DOTALL)
        if match:
            return match.group(1).strip()

    return ""


def run_repoqa_evaluation(
    config: AblationConfig,
    *,
    language: str = "python",
    max_tasks: int | None = None,
    progress_callback=None,
    verbose: bool = False,
) -> list[RepoQAResult]:
    """Run the full RepoQA evaluation for a given config.

    Args:
        config: The ablation configuration to evaluate.
        language: Programming language subset (default: python).
        max_tasks: Limit number of tasks (for debugging).
        progress_callback: Called with (current, total, result) after each task.

    Returns:
        List of per-task results.
    """
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_dataset(language)

    if max_tasks:
        tasks = tasks[:max_tasks]

    results = []
    for i, task in enumerate(tasks):
        logger.info(f"[{i+1}/{len(tasks)}] {task.repo} :: {task.function_name}")
        result = evaluate_task_navigation(task, config, REPOS_DIR, verbose=verbose)
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(tasks), result)

    return results


def compute_metrics(results: list[RepoQAResult]) -> dict[str, Any]:
    """Compute aggregate metrics from RepoQA results."""
    total = len(results)
    if total == 0:
        return {"pass_rate": 0.0, "total": 0, "passed": 0, "failed": 0, "errors": 0}

    passed = sum(1 for r in results if r.passed)
    errors = sum(1 for r in results if not r.run_result.success)
    avg_bleu = sum(r.bleu_score for r in results) / total
    avg_duration = sum(r.run_result.duration_s for r in results) / total

    return {
        "pass_rate": passed / total,
        "total": total,
        "passed": passed,
        "failed": total - passed - errors,
        "errors": errors,
        "avg_bleu_score": round(avg_bleu, 4),
        "avg_duration_s": round(avg_duration, 2),
    }
