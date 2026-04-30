"""Tests for scanner.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.scanner import scan_repo

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


def test_scan_repo_finds_python_files():
    records = scan_repo(SAMPLE_REPO)
    paths = [r.path for r in records]
    assert "models.py" in paths
    assert "services.py" in paths
    assert "utils.py" in paths


def test_scan_repo_collects_metadata():
    records = scan_repo(SAMPLE_REPO)
    models = next(r for r in records if r.path == "models.py")
    assert models.language == "python"
    assert models.size_bytes > 0
    assert models.line_count > 0


def test_scan_repo_respects_ignore_dirs():
    records = scan_repo(SAMPLE_REPO, ignore_dirs={"__pycache__", ".git"})
    paths = [r.path for r in records]
    for p in paths:
        assert "__pycache__" not in p
        assert ".git" not in p


def test_scan_repo_returns_file_records():
    records = scan_repo(SAMPLE_REPO)
    assert len(records) >= 3
    for r in records:
        assert r.path.endswith(".py")
