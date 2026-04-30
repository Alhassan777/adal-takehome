"""Tests for learned_tools.py -- LearnedToolRegistry lifecycle."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codebase_agent.workflows.learned_tools import LearnedToolRegistry


@pytest.fixture
def temp_cache():
    """Create a temporary cache directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_client():
    """Mock OpenAI client."""
    client = MagicMock()
    return client


@pytest.fixture
def registry(temp_cache, mock_client):
    """Create a LearnedToolRegistry with temp storage."""
    return LearnedToolRegistry(temp_cache, mock_client)


VALID_TOOL_CODE = '''def add_numbers(a=0, b=0):
    """Add two numbers together."""
    return a + b
'''

VALID_TEST_CASES = [
    {"input": {"a": 2, "b": 3}, "expected_contains": "5"},
    {"input": {"a": 0, "b": 0}, "expected_contains": "0"},
]


class TestDeterministicValidation:
    def test_rejects_syntax_errors(self, registry):
        result = registry._validate_deterministic(
            "bad_tool", "def bad_tool( ???", []
        )
        assert not result["passed"]
        assert "Syntax error" in result["error"]

    def test_rejects_missing_function(self, registry):
        result = registry._validate_deterministic(
            "my_tool", "x = 42", []
        )
        assert not result["passed"]
        assert "must define a function" in result["error"]

    def test_rejects_non_callable(self, registry):
        result = registry._validate_deterministic(
            "my_tool", "my_tool = 42", []
        )
        assert not result["passed"]
        assert "not callable" in result["error"]

    def test_passes_valid_code_no_tests(self, registry):
        result = registry._validate_deterministic("add_numbers", VALID_TOOL_CODE, [])
        assert result["passed"]

    def test_passes_valid_code_with_passing_tests(self, registry):
        result = registry._validate_deterministic("add_numbers", VALID_TOOL_CODE, VALID_TEST_CASES)
        assert result["passed"]
        assert len(result["test_results"]) == 2
        assert all(t["passed"] for t in result["test_results"])

    def test_rejects_failing_tests(self, registry):
        bad_tests = [{"input": {"a": 1, "b": 1}, "expected_contains": "99"}]
        result = registry._validate_deterministic("add_numbers", VALID_TOOL_CODE, bad_tests)
        assert not result["passed"]
        assert "failed" in result["error"]


class TestObserverCritic:
    def test_calls_openai_with_correct_model(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "correctness": 5,
            "generalizability": 4,
            "non_redundancy": 4,
            "safety": 5,
            "overall_score": 4.5,
            "approved": True,
            "feedback": "Good tool",
        })
        mock_client.chat.completions.create.return_value = mock_response

        result = registry._observer_critic("add_numbers", VALID_TOOL_CODE, "Add numbers", [])
        assert result["approved"] is True
        assert result["overall_score"] == 4.5

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_handles_critic_failure_gracefully(self, registry, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = registry._observer_critic("tool", "code", "desc", [])
        assert result["approved"] is False
        assert "failed" in result["feedback"]


class TestProposeToolLifecycle:
    def test_full_approval_lifecycle(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "correctness": 5,
            "generalizability": 4,
            "non_redundancy": 4,
            "safety": 5,
            "overall_score": 4.5,
            "approved": True,
            "feedback": "Useful tool",
        })
        mock_client.chat.completions.create.return_value = mock_response

        result = registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add numbers", VALID_TEST_CASES)
        assert result["approved"] is True
        assert "approved and saved" in result["feedback"]

        assert registry.manifest_path.exists()
        manifest = json.loads(registry.manifest_path.read_text())
        assert len(manifest) == 1
        assert manifest[0]["name"] == "add_numbers"

        tool_file = registry.tools_dir / "add_numbers.py"
        assert tool_file.exists()
        assert tool_file.read_text() == VALID_TOOL_CODE

    def test_rejects_duplicate_name(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add", VALID_TEST_CASES)
        result = registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add again", VALID_TEST_CASES)
        assert result["approved"] is False
        assert "already exists" in result["feedback"]

    def test_rejects_when_critic_disapproves(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "correctness": 2,
            "generalizability": 1,
            "non_redundancy": 2,
            "safety": 3,
            "overall_score": 2.0,
            "approved": False,
            "feedback": "Too specific to one codebase",
        })
        mock_client.chat.completions.create.return_value = mock_response

        result = registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add", VALID_TEST_CASES)
        assert result["approved"] is False
        assert "rejected" in result["feedback"]


class TestGetActiveTools:
    def test_returns_callable_tools(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add", VALID_TEST_CASES)
        active = registry.get_active_tools("hash123")

        assert "add_numbers" in active
        assert callable(active["add_numbers"])
        assert active["add_numbers"](a=3, b=7) == 10

    def test_handles_missing_tool_file(self, registry, temp_cache):
        registry._manifest = [{"name": "ghost", "file": "ghost.py"}]
        active = registry.get_active_tools("hash123")
        assert "ghost" not in active


class TestInjectIntoNamespace:
    def test_injects_tools_with_prefix(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add", VALID_TEST_CASES)

        namespace = {}
        registry.inject_into_namespace(namespace, "hash123")

        assert "learned_add_numbers" in namespace
        assert callable(namespace["learned_add_numbers"])
        assert "register_tool" in namespace
        assert namespace["register_tool"] == registry.propose_tool


class TestUsageTelemetry:
    def test_record_usage_updates_counts(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add", VALID_TEST_CASES)

        registry.record_usage("add_numbers")
        registry.record_usage("add_numbers")
        registry.record_usage("add_numbers")

        manifest = json.loads(registry.manifest_path.read_text())
        assert manifest[0]["use_count"] == 3


class TestLRUEviction:
    def test_evicts_lru_when_cap_exceeded(self, temp_cache, mock_client):
        from codebase_agent.config import MAX_LEARNED_TOOLS

        registry = LearnedToolRegistry(temp_cache, mock_client)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        for i in range(MAX_LEARNED_TOOLS + 3):
            code = f'def tool_{i}():\n    return {i}\n'
            tests = [{"input": {}, "expected_contains": str(i)}]
            registry.propose_tool(f"tool_{i}", code, f"Tool {i}", tests)

        assert len(registry._manifest) == MAX_LEARNED_TOOLS


class TestListTools:
    def test_returns_metadata(self, registry, mock_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "ok",
        })
        mock_client.chat.completions.create.return_value = mock_response

        registry.propose_tool("add_numbers", VALID_TOOL_CODE, "Add numbers", VALID_TEST_CASES)
        tools = registry.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "add_numbers"
        assert tools[0]["description"] == "Add numbers"
        assert tools[0]["critic_score"] == 4.5
