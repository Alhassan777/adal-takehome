"""Core framework for generating synthetic repositories with ground truth.

Each challenge module produces a SyntheticRepo -- a collection of files and
questions with known-correct answers -- that can be materialized on disk and
evaluated against the codebase navigation agent.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SizeTier(str, Enum):
    XS = "XS"   # 3-5 files,   ~50-100 lines
    S = "S"     # 10-15 files,  ~300-500 lines
    M = "M"     # 30-50 files,  ~1500-3000 lines
    L = "L"     # 80-120 files, ~5000-10000 lines
    XL = "XL"   # 200+ files,   ~15000+ lines


class ScoringMethod(str, Enum):
    FILE_AND_SYMBOL_MATCH = "file_and_symbol_match"
    FILE_SET_MATCH = "file_set_match"
    ORDERED_LIST_MATCH = "ordered_list_match"
    SYMBOL_SET_MATCH = "symbol_set_match"
    RISK_LEVEL_MATCH = "risk_level_match"
    CONTAINS_KEYWORDS = "contains_keywords"
    BOOLEAN_MATCH = "boolean_match"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class GroundTruthQuestion:
    """A single question with a known-correct answer."""

    id: str
    question: str
    workflow_type: str
    expected: dict[str, Any]
    scoring: ScoringMethod
    difficulty: Difficulty = Difficulty.MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "workflow_type": self.workflow_type,
            "expected": self.expected,
            "scoring": self.scoring.value,
            "difficulty": self.difficulty.value,
        }


@dataclass
class SyntheticRepo:
    """A complete synthetic repository ready to be written to disk."""

    repo_id: str
    challenge: str
    size_tier: SizeTier
    files: dict[str, str]  # relative path -> file content
    questions: list[GroundTruthQuestion] = field(default_factory=list)
    description: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_lines(self) -> int:
        return sum(content.count("\n") + 1 for content in self.files.values())

    def to_ground_truth(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "challenge": self.challenge,
            "size_tier": self.size_tier.value,
            "description": self.description,
            "file_count": self.file_count,
            "line_count": self.total_lines,
            "questions": [q.to_dict() for q in self.questions],
        }


def write_repo(repo: SyntheticRepo, target_dir: Path | None = None) -> Path:
    """Materialize a SyntheticRepo on disk. Returns the repo root path.

    If target_dir is None, creates a temp directory.
    """
    if target_dir is None:
        target_dir = Path(tempfile.mkdtemp(prefix=f"synth_{repo.repo_id}_"))
    else:
        target_dir = target_dir / repo.repo_id
        target_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in repo.files.items():
        file_path = target_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    gt_path = target_dir / "ground_truth.json"
    gt_path.write_text(
        json.dumps(repo.to_ground_truth(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return target_dir


def cleanup_repo(repo_dir: Path) -> None:
    """Remove a materialized synthetic repo from disk."""
    shutil.rmtree(repo_dir, ignore_errors=True)


def _make_init(imports: list[str] | None = None) -> str:
    """Helper: generate an __init__.py with optional imports."""
    if not imports:
        return ""
    lines = [f"from .{name} import *" for name in imports]
    return "\n".join(lines) + "\n"


def _pad_with_helpers(base_content: str, target_lines: int, prefix: str = "helper") -> str:
    """Pad a file with realistic-looking helper functions to reach a target line count.

    Used by challenge generators to scale repos to larger size tiers.
    """
    current = base_content.count("\n") + 1
    if current >= target_lines:
        return base_content

    parts = [base_content, "\n"]
    idx = 0
    while current < target_lines:
        func = (
            f"\n\ndef {prefix}_{idx}(data):\n"
            f'    """Process data item {idx}."""\n'
            f"    result = {{}}\n"
            f"    for key, value in data.items():\n"
            f"        result[key] = str(value).strip()\n"
            f"    return result\n"
        )
        parts.append(func)
        current += func.count("\n") + 1
        idx += 1

    return "".join(parts)


def _make_class(
    name: str,
    bases: list[str] | None = None,
    methods: list[tuple[str, str]] | None = None,
    docstring: str = "",
) -> str:
    """Helper: generate a class definition string."""
    base_str = f"({', '.join(bases)})" if bases else ""
    lines = [f"class {name}{base_str}:"]
    if docstring:
        lines.append(f'    """{docstring}"""')
    lines.append("")
    if methods:
        for method_name, body in methods:
            lines.append(f"    def {method_name}(self):")
            for body_line in body.strip().split("\n"):
                lines.append(f"        {body_line}")
            lines.append("")
    else:
        lines.append("    pass")
    return "\n".join(lines) + "\n"


def _make_function(name: str, params: str = "", body: str = "pass", docstring: str = "") -> str:
    """Helper: generate a function definition string."""
    lines = [f"def {name}({params}):"]
    if docstring:
        lines.append(f'    """{docstring}"""')
    for body_line in body.strip().split("\n"):
        lines.append(f"    {body_line}")
    return "\n".join(lines) + "\n"
