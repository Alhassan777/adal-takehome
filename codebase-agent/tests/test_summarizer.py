"""Tests for summarizer.py."""

import json
import sys
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.intelligence.summarizer import (
    _build_llm_prompt,
    _extract_route_path,
    _FactBundle,
    _merge_llm_into_summary,
    _parse_llm_response,
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


# ---------------------------------------------------------------------------
# LLM summary path tests (mocked OpenAI)
# ---------------------------------------------------------------------------


def _make_llm_response(files: list[dict]) -> str:
    return json.dumps({"files": files})


def _mock_openai_create(response_json: str):
    """Build a mock that replaces client.chat.completions.create(...)."""
    mock_message = MagicMock()
    mock_message.content = response_json
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_build_llm_prompt_formatting():
    facts = _FactBundle()
    facts.main_classes = ["AuthManager"]
    facts.main_functions = ["verify_token", "refresh"]
    facts.depends_on = ["jwt", "redis"]
    facts.docstrings = ["Handles authentication."]

    prompt = _build_llm_prompt([("src/auth.py", facts)])
    assert "File 1: src/auth.py" in prompt
    assert "AuthManager" in prompt
    assert "verify_token" in prompt
    assert "jwt" in prompt
    assert "Handles authentication." in prompt


def test_build_llm_prompt_test_file():
    facts = _FactBundle()
    facts.has_test_markers = True
    facts.main_functions = ["test_login"]

    prompt = _build_llm_prompt([("tests/test_auth.py", facts)])
    assert "This is a test file." in prompt


def test_parse_llm_response_valid():
    raw = _make_llm_response([
        {"path": "a.py", "purpose": "Does A.", "responsibilities": ["handles A", "manages B"]},
        {"path": "b.py", "purpose": "Does B.", "responsibilities": ["serves C"]},
    ])
    result = _parse_llm_response(raw, ["a.py", "b.py"])
    assert "a.py" in result
    assert result["a.py"][0] == "Does A."
    assert len(result["a.py"][1]) == 2
    assert "b.py" in result


def test_parse_llm_response_malformed_json():
    result = _parse_llm_response("not json at all", ["a.py"])
    assert result == {}


def test_parse_llm_response_missing_fields():
    raw = json.dumps({"files": [{"path": "a.py"}]})
    result = _parse_llm_response(raw, ["a.py"])
    assert "a.py" not in result


def test_parse_llm_response_wrong_structure():
    raw = json.dumps({"files": "not a list"})
    result = _parse_llm_response(raw, ["a.py"])
    assert result == {}


def test_merge_llm_into_summary():
    facts = _FactBundle()
    facts.main_classes = ["UserService"]
    facts.main_functions = ["get_user", "delete_user"]
    facts.depends_on = ["sqlalchemy", "pydantic"]
    facts.used_by = ["api/routes.py"]
    facts.side_effects = ["delete_user may delete"]
    facts.external_services = []
    facts.data_models = []

    summary = _merge_llm_into_summary(
        "services/user.py",
        facts,
        ("Manages user lifecycle.", ["CRUD operations", "Validates input"]),
    )
    assert summary.purpose == "Manages user lifecycle."
    assert summary.responsibilities == ["CRUD operations", "Validates input"]
    assert summary.confidence == 0.9
    assert "llm" in summary.generated_from
    assert "UserService" in summary.main_symbols
    assert "sqlalchemy" in summary.depends_on
    assert "api/routes.py" in summary.used_by
    assert "delete_user may delete" in summary.side_effects


@patch("codebase_agent.intelligence.summarizer._get_openai_client")
def test_build_summaries_with_llm(mock_get_client):
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    file_paths = [f.path for f in idx.files]

    llm_files = [
        {"path": p, "purpose": f"LLM summary for {p}.", "responsibilities": ["Does things"]}
        for p in file_paths
    ]
    response_json = _make_llm_response(llm_files)
    mock_get_client.return_value = _mock_openai_create(response_json)

    summaries = build_summaries(idx, SAMPLE_REPO, use_llm=True)
    assert len(summaries) >= 3
    for s in summaries:
        assert s.purpose.startswith("LLM summary for")
        assert s.confidence == 0.9
        assert "llm" in s.generated_from
    _cleanup()


@patch("codebase_agent.intelligence.summarizer._get_openai_client")
def test_build_summaries_llm_fallback_on_api_failure(mock_get_client):
    _cleanup()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("API down")
    mock_get_client.return_value = mock_client

    idx = build_index(SAMPLE_REPO)
    summaries = build_summaries(idx, SAMPLE_REPO, use_llm=True)
    assert len(summaries) >= 3
    for s in summaries:
        assert s.confidence < 0.9
        assert "llm" not in s.generated_from
    _cleanup()


@patch("codebase_agent.intelligence.summarizer._get_openai_client")
def test_build_summaries_llm_fallback_no_client(mock_get_client):
    _cleanup()
    mock_get_client.return_value = None

    idx = build_index(SAMPLE_REPO)
    summaries = build_summaries(idx, SAMPLE_REPO, use_llm=True)
    assert len(summaries) >= 3
    for s in summaries:
        assert "llm" not in s.generated_from
    _cleanup()


@patch("codebase_agent.intelligence.summarizer._get_openai_client")
def test_build_summaries_llm_partial_response(mock_get_client):
    """LLM returns summaries for only some files; rest fall back to heuristic."""
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    first_path = idx.files[0].path

    llm_files = [
        {"path": first_path, "purpose": "LLM got this one.", "responsibilities": ["A thing"]},
    ]
    response_json = _make_llm_response(llm_files)
    mock_get_client.return_value = _mock_openai_create(response_json)

    summaries = build_summaries(idx, SAMPLE_REPO, use_llm=True)
    llm_count = sum(1 for s in summaries if "llm" in s.generated_from)
    heuristic_count = sum(1 for s in summaries if "llm" not in s.generated_from)
    assert llm_count >= 1
    assert heuristic_count >= 1
    _cleanup()


# ---------------------------------------------------------------------------
# Route decorator detection tests
# ---------------------------------------------------------------------------


def test_extract_route_path_standard():
    assert _extract_route_path('@app.get("/users")') == "/users"
    assert _extract_route_path("@app.post('/items')") == "/items"
    assert _extract_route_path('@router.delete("/users/{id}")') == "/users/{id}"


def test_extract_route_path_no_parens():
    assert _extract_route_path("@app.get") == ""


def test_extract_route_path_no_string_arg():
    assert _extract_route_path("@app.get()") == ""


def test_route_detection_in_facts():
    from codebase_agent.intelligence.summarizer import _extract_facts
    from codebase_agent.models import SymbolRecord, RepoIndex

    symbols = [
        SymbolRecord(
            name="list_users", qualified_name="list_users", kind="function",
            file_path="api.py", line_start=1, line_end=3,
            decorators=['@app.get("/users")'],
        ),
        SymbolRecord(
            name="create_user", qualified_name="create_user", kind="function",
            file_path="api.py", line_start=5, line_end=7,
            decorators=['@app.post("/users")'],
        ),
        SymbolRecord(
            name="helper", qualified_name="helper", kind="function",
            file_path="api.py", line_start=9, line_end=11,
            decorators=[],
        ),
    ]
    index = RepoIndex(root_path=".", files=[], symbols=symbols, imports=[])
    facts = _extract_facts("api.py", symbols, [], index)

    assert facts.has_route_decorators is True
    assert len(facts.routes) == 2
    assert "/users" in facts.routes


def test_route_detection_purpose_sentence():
    from codebase_agent.intelligence.summarizer import _extract_facts, _generate_file_summary
    from codebase_agent.models import SymbolRecord, RepoIndex

    symbols = [
        SymbolRecord(
            name="list_users", qualified_name="list_users", kind="function",
            file_path="routes.py", line_start=1, line_end=3,
            decorators=['@router.get("/users")'],
        ),
        SymbolRecord(
            name="create_user", qualified_name="create_user", kind="function",
            file_path="routes.py", line_start=5, line_end=7,
            decorators=['@router.post("/users")'],
        ),
        SymbolRecord(
            name="delete_user", qualified_name="delete_user", kind="function",
            file_path="routes.py", line_start=9, line_end=11,
            decorators=['@router.delete("/users/{id}")'],
        ),
    ]
    index = RepoIndex(root_path=".", files=[], symbols=symbols, imports=[])
    facts = _extract_facts("routes.py", symbols, [], index)
    summary = _generate_file_summary("routes.py", facts)

    assert "3 API endpoints" in summary.purpose
    assert "Provides" in summary.purpose


def test_no_route_decorators_no_flag():
    from codebase_agent.intelligence.summarizer import _extract_facts
    from codebase_agent.models import SymbolRecord, RepoIndex

    symbols = [
        SymbolRecord(
            name="helper", qualified_name="helper", kind="function",
            file_path="utils.py", line_start=1, line_end=3,
            decorators=["@staticmethod"],
        ),
    ]
    index = RepoIndex(root_path=".", files=[], symbols=symbols, imports=[])
    facts = _extract_facts("utils.py", symbols, [], index)

    assert facts.has_route_decorators is False
    assert facts.routes == []


def test_llm_prompt_includes_routes():
    facts = _FactBundle()
    facts.has_route_decorators = True
    facts.routes = ["/users", "/users/{id}", "/items"]
    facts.main_functions = ["list_users", "get_user", "list_items"]

    prompt = _build_llm_prompt([("api/main.py", facts)])
    assert "3 HTTP route(s)" in prompt
    assert "/users" in prompt
