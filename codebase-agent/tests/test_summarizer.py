"""Tests for summarizer.py."""

import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.intelligence.summarizer import (
    build_summaries,
    get_directory_summary,
    get_file_summary,
    search_summaries,
)
from codebase_agent.config import INDEX_DIR

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


def _cleanup():
    cache_dir = Path(SAMPLE_REPO) / INDEX_DIR
    shutil.rmtree(str(cache_dir), ignore_errors=True)


def test_build_summaries_generates_for_all_files():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    summaries = build_summaries(idx, SAMPLE_REPO)
    assert len(summaries) >= 3
    _cleanup()


def test_file_summary_has_purpose():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    summaries = build_summaries(idx, SAMPLE_REPO)
    for s in summaries:
        assert s.purpose != ""
        assert s.path != ""
    _cleanup()


def test_get_file_summary_returns_summary():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    build_summaries(idx, SAMPLE_REPO)
    summary = get_file_summary(idx, SAMPLE_REPO, "models.py")
    assert summary is not None
    assert "User" in summary.main_symbols or "Task" in summary.main_symbols
    _cleanup()


def test_search_summaries_finds_relevant():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    build_summaries(idx, SAMPLE_REPO)
    results = search_summaries(idx, SAMPLE_REPO, "user")
    assert len(results) > 0
    _cleanup()


def test_directory_summary():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    ds = get_directory_summary(idx, SAMPLE_REPO, ".")
    assert ds.file_count >= 3
    _cleanup()
