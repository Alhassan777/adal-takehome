"""Tests for tools.py."""

import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.config import INDEX_DIR
from codebase_agent.intelligence.tools import (
    find_references,
    find_tests,
    get_call_graph,
    get_definition,
    get_directory_summary,
    get_file_summary,
    get_imports,
    impact_analysis,
    list_tree,
    read_snippet,
    repo_map,
    search_summaries,
    search_symbols_tool,
    search_text_tool,
    trace_module,
)

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


def _cleanup():
    shutil.rmtree(str(Path(SAMPLE_REPO) / INDEX_DIR), ignore_errors=True)


def _get_index():
    return build_index(SAMPLE_REPO)


def test_repo_map_returns_tree():
    _cleanup()
    idx = _get_index()
    result = repo_map(SAMPLE_REPO, idx, depth=2)
    assert result["type"] == "directory"
    _cleanup()


def test_list_tree():
    _cleanup()
    idx = _get_index()
    result = list_tree(SAMPLE_REPO, idx)
    assert result["total_files"] >= 3
    _cleanup()


def test_search_text_tool():
    result = search_text_tool(SAMPLE_REPO, "User")
    assert result["count"] > 0


def test_search_symbols_tool():
    _cleanup()
    idx = _get_index()
    result = search_symbols_tool(idx, "User")
    assert result["count"] > 0
    _cleanup()


def test_get_definition():
    _cleanup()
    idx = _get_index()
    result = get_definition(SAMPLE_REPO, idx, "User")
    assert result["found"] is True
    assert result["definition"]["kind"] == "class"
    _cleanup()


def test_find_references():
    _cleanup()
    idx = _get_index()
    result = find_references(SAMPLE_REPO, idx, "User")
    assert result["count"] >= 0
    _cleanup()


def test_read_snippet():
    result = read_snippet(SAMPLE_REPO, "models.py", 1, 5)
    assert "dataclass" in result["content"] or "from" in result["content"]


def test_get_imports():
    _cleanup()
    idx = _get_index()
    result = get_imports(idx, "services.py")
    assert result["count"] > 0
    _cleanup()


def test_get_call_graph():
    _cleanup()
    idx = _get_index()
    result = get_call_graph(SAMPLE_REPO, idx, "summarize_project")
    assert "calls" in result
    _cleanup()


def test_find_tests_for_file():
    _cleanup()
    idx = _get_index()
    result = find_tests(idx, "models.py")
    assert "test_files" in result
    _cleanup()


def test_impact_analysis():
    _cleanup()
    idx = _get_index()
    result = impact_analysis(SAMPLE_REPO, idx, "User")
    assert "risk" in result
    _cleanup()


def test_get_file_summary():
    _cleanup()
    idx = _get_index()
    result = get_file_summary(idx, SAMPLE_REPO, "models.py")
    assert "path" in result
    _cleanup()


def test_search_summaries():
    _cleanup()
    idx = _get_index()
    result = search_summaries(idx, SAMPLE_REPO, "user")
    assert "results" in result
    _cleanup()


def test_trace_module():
    _cleanup()
    idx = _get_index()
    result = trace_module(SAMPLE_REPO, idx, "services.py")
    assert "depends_on" in result
    _cleanup()
