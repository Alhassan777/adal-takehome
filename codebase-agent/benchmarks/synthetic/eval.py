"""Evaluation adapter: runs the agent against synthetic repos and scores answers.

Follows the same pattern as repoqa_eval.py / dependeval_eval.py so it
integrates cleanly into the existing run_all.py harness.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..configs import AblationConfig
from ..runner import RunResult, run_agent, init_session_for_config
from .generator import (
    GroundTruthQuestion,
    ScoringMethod,
    SyntheticRepo,
    cleanup_repo,
    write_repo,
)
from .repos import CHALLENGES, ALL_SIZES, generate_repo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Result model
# ---------------------------------------------------------------

@dataclass
class SyntheticResult:
    """Result of evaluating a single question against a synthetic repo."""

    repo_id: str
    question_id: str
    question: str
    run_result: RunResult
    scoring_method: str
    score: float  # 0.0 - 1.0
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "question_id": self.question_id,
            "question": self.question,
            "scoring_method": self.scoring_method,
            "score": round(self.score, 4),
            "passed": self.passed,
            "answer": str(self.run_result.answer)[:500] if self.run_result.answer else "",
            "duration_s": self.run_result.duration_s,
            "config_id": self.run_result.config_id,
            "success": self.run_result.success,
            "error": self.run_result.error,
            "details": self.details,
        }


# ---------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------

def _normalize(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return text.lower().strip().replace("\\", "/")


def score_file_and_symbol_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer mentions the correct file and symbol."""
    ans = _normalize(answer)
    file_match = _normalize(expected.get("file", "")) in ans
    symbol = expected.get("symbol", "")
    symbol_match = symbol.lower() in ans

    score = 0.0
    if file_match:
        score += 0.5
    if symbol_match:
        score += 0.5

    return score, {"file_found": file_match, "symbol_found": symbol_match}


def score_file_set_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer mentions the expected set of files (F1 score)."""
    ans = _normalize(answer)

    expected_files = expected.get("files", expected.get("must_include", expected.get("dependents", [])))
    if not expected_files:
        return 1.0, {"note": "no expected files"}

    found = 0
    missing = []
    for f in expected_files:
        if _normalize(f) in ans or _normalize(Path(f).name) in ans:
            found += 1
        else:
            missing.append(f)

    recall = found / len(expected_files) if expected_files else 1.0
    return recall, {"found": found, "total": len(expected_files), "missing": missing}


def score_ordered_list_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer contains files in the correct order."""
    expected_order = expected.get("ordered_files", [])
    if not expected_order:
        return 1.0, {}

    # Extract filenames from the answer in order of appearance
    ans = _normalize(answer)
    positions = []
    for f in expected_order:
        fname = _normalize(Path(f).name)
        pos = ans.find(fname)
        if pos == -1:
            pos = ans.find(_normalize(f))
        positions.append(pos)

    found_positions = [(p, f) for p, f in zip(positions, expected_order) if p >= 0]
    if not found_positions:
        return 0.0, {"found_none": True}

    is_ordered = all(found_positions[i][0] <= found_positions[i+1][0]
                     for i in range(len(found_positions) - 1))
    coverage = len(found_positions) / len(expected_order)
    score = coverage * (1.0 if is_ordered else 0.5)

    return score, {"ordered": is_ordered, "coverage": coverage}


def score_symbol_set_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer mentions the expected set of symbols."""
    ans = _normalize(answer)

    for key in ("public_symbols", "dead_symbols", "untested_files", "public", "symbols"):
        expected_syms = expected.get(key, [])
        if expected_syms:
            break
    else:
        expected_syms = []

    if not expected_syms:
        return 1.0, {}

    found = sum(1 for s in expected_syms if s.lower() in ans)
    recall = found / len(expected_syms)
    return recall, {"found": found, "total": len(expected_syms)}


def score_risk_level_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer contains the expected risk level."""
    ans = _normalize(answer)
    expected_risk = expected.get("risk", "").lower()
    if not expected_risk:
        return 1.0, {}
    match = expected_risk in ans
    return 1.0 if match else 0.0, {"expected_risk": expected_risk, "found": match}


def score_contains_keywords(answer: str, expected: dict) -> tuple[float, dict]:
    """Check if the answer contains required keywords."""
    ans = _normalize(answer)
    keywords = expected.get("keywords", [])
    if not keywords:
        return 1.0, {}

    found = sum(1 for kw in keywords if kw.lower() in ans)
    recall = found / len(keywords)
    return recall, {"found": found, "total": len(keywords)}


def score_boolean_match(answer: str, expected: dict) -> tuple[float, dict]:
    """Flexible check for boolean/count/existence questions."""
    if not isinstance(answer, str):
        answer = str(answer)
    ans = _normalize(answer)

    if "is_dead" in expected:
        target = expected["is_dead"]
        if target:
            match = any(w in ans for w in [
                "dead", "unused", "not used", "never imported", "not imported",
                "no references outside", "not actively used", "not referenced",
                "no other files", "not used elsewhere", "only referenced within",
                "may not be used", "might not be", "never referenced",
                "no references to", "is not actively",
            ])
        else:
            match = any(w in ans for w in [
                "used", "referenced", "imported", "alive", "active",
                "is used", "is referenced", "is imported",
            ])
        matched_phrase = next((w for w in (
            ["dead", "unused", "not used", "never imported", "not imported",
             "no references outside", "not actively used", "not referenced",
             "no other files", "not used elsewhere", "only referenced within",
             "may not be used", "might not be", "never referenced",
             "no references to", "is not actively"] if target else
            ["used", "referenced", "imported", "alive", "active",
             "is used", "is referenced", "is imported"]
        ) if w in ans), None)
        return 1.0 if match else 0.0, {"expected_dead": target, "match": match, "matched_phrase": matched_phrase}

    if "has_tests" in expected:
        target = expected["has_tests"]
        if target:
            match = any(w in ans for w in ["test", "tested", "coverage"])
        else:
            match = any(w in ans for w in [
                "no test", "untested", "not tested", "no coverage", "missing",
                "no specific test", "are no test", "does not have test",
                "doesn't have test", "no dedicated test", "not covered",
                "no matching test",
            ])
        matched_phrase = next((w for w in (
            ["test", "tested", "coverage"] if target else
            ["no test", "untested", "not tested", "no coverage", "missing",
             "no specific test", "are no test", "does not have test",
             "doesn't have test", "no dedicated test", "not covered",
             "no matching test"]
        ) if w in ans), None)
        return 1.0 if match else 0.0, {"expected_has_tests": target, "match": match, "matched_phrase": matched_phrase}

    if "safe_to_delete" in expected:
        target = expected["safe_to_delete"]
        if target:
            match = any(w in ans for w in [
                "safe", "can delete", "unused", "no references",
                "can be removed", "can be safely", "not referenced",
            ])
        else:
            match = any(w in ans for w in [
                "not safe", "used", "referenced", "would break",
                "cannot delete", "should not delete", "is referenced",
            ])
        return 1.0 if match else 0.0, {"expected_safe": target, "match": match}

    if "file_count" in expected:
        expected_count = expected["file_count"]
        numbers = re.findall(r'\b(\d+)\b', answer)
        if str(expected_count) in numbers:
            return 1.0, {"expected_count": expected_count, "found": True, "method": "explicit_number"}
        listed_items = re.findall(r"['\"][\w./]+\.py['\"]", answer)
        if not listed_items:
            listed_items = re.findall(r"\b\w+\.py\b", answer)
        if listed_items and len(listed_items) == expected_count:
            return 1.0, {"expected_count": expected_count, "found": True, "method": "item_count", "items": listed_items}
        return 0.0, {"expected_count": expected_count, "found_numbers": numbers[:5], "listed_items_count": len(listed_items)}

    return 0.5, {"note": "no specific boolean check matched"}


SCORERS = {
    ScoringMethod.FILE_AND_SYMBOL_MATCH: score_file_and_symbol_match,
    ScoringMethod.FILE_SET_MATCH: score_file_set_match,
    ScoringMethod.ORDERED_LIST_MATCH: score_ordered_list_match,
    ScoringMethod.SYMBOL_SET_MATCH: score_symbol_set_match,
    ScoringMethod.RISK_LEVEL_MATCH: score_risk_level_match,
    ScoringMethod.CONTAINS_KEYWORDS: score_contains_keywords,
    ScoringMethod.BOOLEAN_MATCH: score_boolean_match,
}


# ---------------------------------------------------------------
# Evaluation driver
# ---------------------------------------------------------------

def evaluate_question(
    repo_dir: str,
    repo: SyntheticRepo,
    question: GroundTruthQuestion,
    config: AblationConfig,
    *,
    verbose: bool = False,
) -> SyntheticResult:
    """Evaluate a single ground-truth question against the agent."""
    run_result = run_agent(repo_dir, question.question, config, verbose=verbose)

    if not run_result.success:
        return SyntheticResult(
            repo_id=repo.repo_id,
            question_id=question.id,
            question=question.question,
            run_result=run_result,
            scoring_method=question.scoring.value,
            score=0.0,
            passed=False,
            details={"error": run_result.error},
        )

    scoring_method = ScoringMethod(question.scoring) if isinstance(question.scoring, str) else question.scoring
    scorer = SCORERS.get(scoring_method, score_contains_keywords)
    answer_text = run_result.answer if isinstance(run_result.answer, str) else str(run_result.answer)
    score, details = scorer(answer_text, question.expected)
    passed = score >= 0.5

    return SyntheticResult(
        repo_id=repo.repo_id,
        question_id=question.id,
        question=question.question,
        run_result=run_result,
        scoring_method=question.scoring.value,
        score=score,
        passed=passed,
        details=details,
    )


def evaluate_repo(
    repo: SyntheticRepo,
    config: AblationConfig,
    *,
    progress_callback=None,
) -> list[SyntheticResult]:
    """Evaluate all questions for a single synthetic repo."""
    repo_dir = write_repo(repo)
    results = []

    try:
        session = init_session_for_config(str(repo_dir), config)

        for i, question in enumerate(repo.questions):
            logger.info(f"  [{i+1}/{len(repo.questions)}] {question.id}: {question.question[:60]}...")
            result = evaluate_question(str(repo_dir), repo, question, config)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(repo.questions), result)
    finally:
        cleanup_repo(repo_dir)

    return results


def run_synthetic_evaluation(
    config: AblationConfig,
    *,
    challenges: list[str] | None = None,
    sizes: list[str] | None = None,
    max_tasks: int | None = None,
    progress_callback=None,
    verbose: bool = False,
) -> list[SyntheticResult]:
    """Run the full synthetic evaluation for a given config.

    Args:
        config: Ablation configuration.
        challenges: Subset of challenge names (default: all).
        sizes: Subset of size tier names (default: all).
        max_tasks: Limit total number of questions evaluated.
        progress_callback: Called with (current, total, result).

    Returns:
        Flat list of per-question results across all repos.
    """
    from .generator import SizeTier

    target_challenges = challenges or list(CHALLENGES.keys())
    target_sizes = [SizeTier(s) for s in sizes] if sizes else ALL_SIZES

    all_results: list[SyntheticResult] = []
    task_count = 0

    for challenge_name in target_challenges:
        for sz in target_sizes:
            repo = generate_repo(challenge_name, sz)
            logger.info(f"Evaluating {repo.repo_id} ({repo.file_count} files, {len(repo.questions)} questions)")

            for i, question in enumerate(repo.questions):
                if max_tasks and task_count >= max_tasks:
                    return all_results

                repo_dir = write_repo(repo)
                try:
                    result = evaluate_question(str(repo_dir), repo, question, config, verbose=verbose)
                finally:
                    cleanup_repo(repo_dir)

                all_results.append(result)
                task_count += 1

                if progress_callback:
                    progress_callback(task_count, max_tasks or task_count, result)

    return all_results


def compute_metrics(results: list[SyntheticResult]) -> dict[str, Any]:
    """Compute aggregate metrics from synthetic evaluation results."""
    total = len(results)
    if total == 0:
        return {"pass_rate": 0.0, "total": 0, "passed": 0, "avg_score": 0.0, "errors": 0}

    passed = sum(1 for r in results if r.passed)
    errors = sum(1 for r in results if not r.run_result.success)
    avg_score = sum(r.score for r in results) / total
    avg_duration = sum(r.run_result.duration_s for r in results) / total

    # Per-challenge breakdown
    by_challenge: dict[str, dict] = {}
    for r in results:
        challenge = r.repo_id.rsplit("_", 1)[0]
        entry = by_challenge.setdefault(challenge, {"total": 0, "passed": 0, "scores": []})
        entry["total"] += 1
        if r.passed:
            entry["passed"] += 1
        entry["scores"].append(r.score)

    challenge_metrics = {}
    for ch, data in by_challenge.items():
        challenge_metrics[ch] = {
            "pass_rate": data["passed"] / data["total"],
            "avg_score": sum(data["scores"]) / len(data["scores"]),
            "total": data["total"],
            "passed": data["passed"],
        }

    # Per-scoring-method breakdown
    by_scoring: dict[str, dict] = {}
    for r in results:
        entry = by_scoring.setdefault(r.scoring_method, {"total": 0, "passed": 0, "scores": []})
        entry["total"] += 1
        if r.passed:
            entry["passed"] += 1
        entry["scores"].append(r.score)

    scoring_metrics = {}
    for sm, data in by_scoring.items():
        scoring_metrics[sm] = {
            "pass_rate": data["passed"] / data["total"],
            "avg_score": sum(data["scores"]) / len(data["scores"]),
            "total": data["total"],
        }

    return {
        "pass_rate": passed / total,
        "avg_score": round(avg_score, 4),
        "total": total,
        "passed": passed,
        "errors": errors,
        "avg_duration_s": round(avg_duration, 2),
        "by_challenge": challenge_metrics,
        "by_scoring_method": scoring_metrics,
    }
