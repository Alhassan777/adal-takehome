"""SWE-QA benchmark adapter.

Evaluates the agent's ability to answer repository-level code questions
across 15 popular Python repositories (720 QA pairs total).

Uses the SWE-QA-Bench evaluation framework:
  - Questions from Experiment/datasets/questions/{repo}.jsonl
  - Scoring via LLM-as-Judge (5 dimensions, 100-point scale)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .configs import AblationConfig
from .runner import RunResult, run_agent, init_session_for_config

logger = logging.getLogger(__name__)

VENDOR_DIR = Path(__file__).parent / "vendor"
SWEQA_DIR = VENDOR_DIR / "SWE-QA-Bench"
REPOS_DIR = SWEQA_DIR / "datas" / "repos"

SWEQA_REPO_URL = "https://github.com/peng-weihan/SWE-QA-Bench.git"

DEFAULT_REPOS = ["flask", "requests", "pytest"]

SWEQA_PROMPT_TEMPLATE = """\
I have a code repository at {repo_path}. Please answer the following question \
about this repository. Ground your answer in specific file paths, function \
names, and code evidence.

Question: {question}"""


@dataclass
class SWEQATask:
    """A single SWE-QA question."""

    repo_name: str
    question: str
    reference_answer: str


@dataclass
class SWEQAResult:
    """Result of a single SWE-QA evaluation."""

    task: SWEQATask
    run_result: RunResult
    scores: dict[str, int] = field(default_factory=dict)

    @property
    def total_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.task.repo_name,
            "question": self.task.question[:200],
            "answer": self.run_result.answer[:500],
            "reference_answer": self.task.reference_answer[:200],
            "scores": self.scores,
            "total_score": self.total_score,
            "duration_s": self.run_result.duration_s,
            "config_id": self.run_result.config_id,
            "success": self.run_result.success,
            "error": self.run_result.error,
        }


def setup_sweqa_bench() -> bool:
    """Clone SWE-QA-Bench if not present."""
    if SWEQA_DIR.exists() and (SWEQA_DIR / ".git").exists():
        logger.info("SWE-QA-Bench already cloned")
        return True

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Cloning SWE-QA-Bench -> {SWEQA_DIR}")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", SWEQA_REPO_URL, str(SWEQA_DIR)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone SWE-QA-Bench: {e.stderr.decode()}")
        return False


def clone_sweqa_repos(repos: list[str] | None = None) -> dict[str, Path]:
    """Clone target repositories at their pinned commits.

    Returns mapping of repo_name -> local_path.
    """
    repos_file = SWEQA_DIR / "repos.txt"
    if not repos_file.exists():
        logger.warning("repos.txt not found, using dataset directory directly")
        return _discover_repos_from_dataset(repos)

    repo_specs: dict[str, tuple[str, str]] = {}
    with open(repos_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                url, commit = parts[0], parts[1]
                name = url.rstrip("/").split("/")[-1].replace(".git", "")
                repo_specs[name] = (url, commit)

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    cloned: dict[str, Path] = {}

    target_repos = repos if repos else list(repo_specs.keys())

    for repo_name in target_repos:
        if repo_name not in repo_specs:
            logger.warning(f"Repo {repo_name} not in repos.txt, skipping")
            continue

        url, commit = repo_specs[repo_name]
        repo_dir = REPOS_DIR / repo_name

        if repo_dir.exists() and (repo_dir / ".git").exists():
            cloned[repo_name] = repo_dir
            continue

        logger.info(f"Cloning {repo_name} @ {commit[:8]}")
        try:
            subprocess.run(
                ["git", "clone", url, str(repo_dir)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", commit],
                check=True,
                capture_output=True,
                cwd=str(repo_dir),
            )
            cloned[repo_name] = repo_dir
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone {repo_name}: {e.stderr.decode()}")

    return cloned


def _discover_repos_from_dataset(repos: list[str] | None) -> dict[str, Path]:
    """Fallback: find repos already present in the data directory."""
    cloned = {}
    if REPOS_DIR.exists():
        for d in REPOS_DIR.iterdir():
            if d.is_dir() and (d / ".git").exists():
                if repos is None or d.name in repos:
                    cloned[d.name] = d
    return cloned


def load_questions(repos: list[str] | None = None) -> list[SWEQATask]:
    """Load questions from the SWE-QA-Bench dataset."""
    tasks = []

    questions_dir = SWEQA_DIR / "Experiment" / "datasets" / "questions"
    if not questions_dir.exists():
        questions_dir = SWEQA_DIR / "datasets" / "questions"
    if not questions_dir.exists():
        for candidate in SWEQA_DIR.rglob("questions"):
            if candidate.is_dir():
                questions_dir = candidate
                break

    if not questions_dir.exists():
        logger.error(f"Questions directory not found in {SWEQA_DIR}")
        return tasks

    for jsonl_file in sorted(questions_dir.glob("*.jsonl")):
        repo_name = jsonl_file.stem
        if repos and repo_name not in repos:
            continue

        with open(jsonl_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                tasks.append(SWEQATask(
                    repo_name=repo_name,
                    question=data.get("question", ""),
                    reference_answer=data.get("answer", ""),
                ))

    logger.info(f"Loaded {len(tasks)} SWE-QA questions across {len(set(t.repo_name for t in tasks))} repos")
    return tasks


def evaluate_task(
    task: SWEQATask,
    config: AblationConfig,
    repo_paths: dict[str, Path],
) -> SWEQAResult:
    """Evaluate a single SWE-QA task."""
    repo_path = repo_paths.get(task.repo_name)
    if repo_path is None:
        return SWEQAResult(
            task=task,
            run_result=RunResult(
                question=task.question,
                answer="",
                config_id=config.name,
                repo_path="",
                duration_s=0.0,
                success=False,
                error=f"Repo not found: {task.repo_name}",
            ),
        )

    prompt = SWEQA_PROMPT_TEMPLATE.format(
        repo_path=str(repo_path),
        question=task.question,
    )

    run_result = run_agent(str(repo_path), prompt, config)

    return SWEQAResult(task=task, run_result=run_result)


def score_results_llm_judge(
    results: list[SWEQAResult],
    output_dir: Path,
) -> list[SWEQAResult]:
    """Score results using LLM-as-Judge.

    Writes candidate answers to JSONL, invokes the judge, and reads scores back.
    If the SWE-QA scoring script is unavailable, falls back to simple heuristic scoring.
    """
    judge_script = SWEQA_DIR / "Benchmark construction" / "score" / "llm-as-a-judge.py"
    if not judge_script.exists():
        judge_script = SWEQA_DIR / "score" / "main.py"

    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    by_repo: dict[str, list[SWEQAResult]] = {}
    for r in results:
        by_repo.setdefault(r.task.repo_name, []).append(r)

    for repo_name, repo_results in by_repo.items():
        candidate_file = candidates_dir / f"{repo_name}.jsonl"
        with open(candidate_file, "w") as f:
            for r in repo_results:
                f.write(json.dumps({
                    "question": r.task.question,
                    "answer": r.run_result.answer,
                }) + "\n")

    if judge_script.exists():
        logger.info("Running LLM-as-Judge scoring...")
        try:
            env = os.environ.copy()
            env["EVAL_CANDIDATE_DIR"] = str(candidates_dir)
            env["EVAL_OUTPUT_PATH"] = str(output_dir / "scores")

            subprocess.run(
                [sys.executable, str(judge_script)],
                env=env,
                check=True,
                capture_output=True,
                timeout=600,
            )
            return _read_scores(results, output_dir / "scores")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"LLM judge failed, using heuristic scoring: {e}")

    return _heuristic_score(results)


def _read_scores(results: list[SWEQAResult], scores_dir: Path) -> list[SWEQAResult]:
    """Read scores from judge output and attach to results."""
    score_map: dict[str, dict[str, int]] = {}

    for score_file in scores_dir.glob("*.jsonl"):
        with open(score_file) as f:
            for line in f:
                data = json.loads(line.strip())
                q = data.get("question", "")
                s = data.get("score", {})
                score_map[q[:100]] = s

    for r in results:
        key = r.task.question[:100]
        if key in score_map:
            r.scores = score_map[key]

    return results


def _heuristic_score(results: list[SWEQAResult]) -> list[SWEQAResult]:
    """Fallback heuristic scoring when LLM judge is unavailable.

    Scores based on: answer length, file path mentions, and keyword overlap.
    """
    for r in results:
        if not r.run_result.success or not r.run_result.answer:
            r.scores = {"correctness": 0, "completeness": 0, "relevance": 0, "clarity": 0, "reasoning": 0}
            continue

        answer = r.run_result.answer
        ref = r.task.reference_answer

        has_file_refs = ".py" in answer or "line " in answer.lower()
        ref_words = set(ref.lower().split()) if ref else set()
        ans_words = set(answer.lower().split())
        overlap = len(ref_words & ans_words) / max(len(ref_words), 1)

        length_score = min(len(answer) / max(len(ref), 1), 1.5)

        base = 8
        r.scores = {
            "correctness": min(20, int(base + overlap * 12)),
            "completeness": min(20, int(base + length_score * 6 + overlap * 4)),
            "relevance": min(20, int(base + 8 if has_file_refs else base + 2)),
            "clarity": min(20, int(base + min(len(answer), 500) / 100)),
            "reasoning": min(20, int(base + overlap * 8)),
        }

    return results


def run_sweqa_evaluation(
    config: AblationConfig,
    *,
    max_tasks: int | None = None,
    repos: list[str] | None = None,
    progress_callback=None,
) -> list[SWEQAResult]:
    """Run the full SWE-QA evaluation for a given config."""
    if not setup_sweqa_bench():
        logger.error("Failed to set up SWE-QA-Bench")
        return []

    target_repos = repos or DEFAULT_REPOS
    repo_paths = clone_sweqa_repos(target_repos)

    if not repo_paths:
        logger.error("No repos available for evaluation")
        return []

    tasks = load_questions(target_repos)
    if max_tasks:
        tasks = tasks[:max_tasks]

    results = []
    for i, task in enumerate(tasks):
        logger.info(f"[{i+1}/{len(tasks)}] {task.repo_name}: {task.question[:60]}...")
        result = evaluate_task(task, config, repo_paths)
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(tasks), result)

    output_dir = Path(__file__).parent / "results" / "sweqa_scoring" / config.name
    output_dir.mkdir(parents=True, exist_ok=True)
    results = score_results_llm_judge(results, output_dir)

    return results


def compute_metrics(results: list[SWEQAResult]) -> dict[str, Any]:
    """Compute aggregate metrics from SWE-QA results."""
    total = len(results)
    if total == 0:
        return {"avg_score": 0.0, "total": 0, "errors": 0}

    errors = sum(1 for r in results if not r.run_result.success)
    scored = [r for r in results if r.scores]

    if not scored:
        return {"avg_score": 0.0, "total": total, "errors": errors, "scored": 0}

    avg_total = sum(r.total_score for r in scored) / len(scored)

    dimension_avgs = {}
    for dim in ["correctness", "completeness", "relevance", "clarity", "reasoning"]:
        vals = [r.scores.get(dim, 0) for r in scored]
        dimension_avgs[f"avg_{dim}"] = round(sum(vals) / len(vals), 2) if vals else 0

    avg_duration = sum(r.run_result.duration_s for r in results) / total

    return {
        "avg_score": round(avg_total, 2),
        "total": total,
        "scored": len(scored),
        "errors": errors,
        "avg_duration_s": round(avg_duration, 2),
        **dimension_avgs,
    }
