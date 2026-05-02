"""Integration tests for the RLM tool suggestion + user approval flow."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from codebase_agent.logging.user_logger import UserLogger
from codebase_agent.workflows.learned_tools import LearnedToolRegistry


SAMPLE_PROPOSAL = {
    "name": "find_auth_symbols",
    "description": "Find all auth-related symbols in the codebase.",
    "code": "def find_auth_symbols(index):\n    return [s for s in index.symbols if 'auth' in s.name.lower()]",
    "test_cases": [{"input": {}, "expected_contains": ""}],
    "rationale": "Reusable pattern for finding auth code.",
}


class TestUserLoggerToolSuggestions:
    """Verify UserLogger renders tool suggestion UI correctly."""

    def _make_logger(self) -> tuple[UserLogger, StringIO]:
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        logger = UserLogger(verbosity="normal", console=c)
        return logger, buf

    def test_show_tool_suggestions_header(self):
        logger, buf = self._make_logger()
        logger.show_tool_suggestions_header(2)
        output = buf.getvalue()
        assert "Suggested Tools" in output
        assert "2" in output

    def test_show_tool_proposal(self):
        logger, buf = self._make_logger()
        logger.show_tool_proposal(1, SAMPLE_PROPOSAL)
        output = buf.getvalue()
        assert "find_auth_symbols" in output
        assert "Find all auth-related" in output
        assert "Rationale:" in output

    def test_show_tool_promotion_result_approved(self):
        logger, buf = self._make_logger()
        logger.show_tool_promotion_result("my_tool", {
            "approved": True,
            "feedback": "Tool 'my_tool' approved and saved. Score: 4.2/5.0",
        })
        output = buf.getvalue()
        assert "Validated" in output
        assert "4.2" in output

    def test_show_tool_promotion_result_rejected(self):
        logger, buf = self._make_logger()
        logger.show_tool_promotion_result("my_tool", {
            "approved": False,
            "feedback": "Critic rejected: too specific",
        })
        output = buf.getvalue()
        assert "Rejected" in output
        assert "too specific" in output

    def test_show_tool_skipped(self):
        logger, buf = self._make_logger()
        logger.show_tool_skipped("my_tool")
        output = buf.getvalue()
        assert "Skipped" in output

    def test_quiet_mode_suppresses_all(self):
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        logger = UserLogger(verbosity="quiet", console=c)

        logger.show_tool_suggestions_header(1)
        logger.show_tool_proposal(1, SAMPLE_PROPOSAL)
        logger.show_tool_promotion_result("t", {"approved": True, "feedback": "ok"})
        logger.show_tool_skipped("t")

        assert buf.getvalue() == ""


class TestPresentToolSuggestions:
    """Test the CLI _present_tool_suggestions helper."""

    def test_skips_when_no_suggestions(self):
        from codebase_agent.cli.main import _present_tool_suggestions

        _present_tool_suggestions({"answer": "hello"}, "/tmp", None)

    def test_skips_empty_suggestions_list(self):
        from codebase_agent.cli.main import _present_tool_suggestions

        _present_tool_suggestions({"suggested_tools": []}, "/tmp", None)

    @patch("builtins.input", return_value="y")
    @patch("openai.OpenAI")
    def test_approves_tool_on_yes(self, mock_openai_cls, mock_input):
        from codebase_agent.cli.main import _present_tool_suggestions

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "overall_score": 4.5, "approved": True, "feedback": "Good tool",
        })
        mock_client.chat.completions.create.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            result = {
                "suggested_tools": [{
                    "name": "add_numbers",
                    "description": "Add two numbers.",
                    "code": "def add_numbers(a=0, b=0):\n    return a + b\n",
                    "test_cases": [{"input": {"a": 1, "b": 2}, "expected_contains": "3"}],
                    "rationale": "Useful math tool.",
                }],
            }

            buf = StringIO()
            c = Console(file=buf, force_terminal=True, width=120)
            logger = UserLogger(verbosity="normal", console=c)

            _present_tool_suggestions(result, tmpdir, logger)

            output = buf.getvalue()
            assert "add_numbers" in output

    @patch("builtins.input", return_value="n")
    @patch("openai.OpenAI")
    def test_skips_tool_on_no(self, mock_openai_cls, mock_input):
        from codebase_agent.cli.main import _present_tool_suggestions

        with tempfile.TemporaryDirectory() as tmpdir:
            result = {"suggested_tools": [SAMPLE_PROPOSAL]}

            buf = StringIO()
            c = Console(file=buf, force_terminal=True, width=120)
            logger = UserLogger(verbosity="normal", console=c)

            _present_tool_suggestions(result, tmpdir, logger)

            output = buf.getvalue()
            assert "Skipped" in output


class TestRLMEngineToolReflection:
    """Verify the RLM engine includes suggested_tools in results."""

    @patch("codebase_agent.workflows.rlm_engine.ToolReflector")
    def test_reflect_called_after_answer(self, mock_reflector_cls):
        from codebase_agent.workflows.tool_reflector import ToolProposal

        mock_reflector = MagicMock()
        mock_reflector.reflect.return_value = [
            ToolProposal(
                name="test_tool",
                description="A test tool",
                code="def test_tool(): return 42",
                test_cases=[{"input": {}, "expected_contains": "42"}],
                rationale="Testing.",
            ),
        ]
        mock_reflector_cls.return_value = mock_reflector

        from codebase_agent.workflows.rlm_engine import RLMEngine

        mock_index = MagicMock()
        mock_index.files = []

        with patch.object(RLMEngine, "_build_tool_registry", return_value={}):
            engine = RLMEngine.__new__(RLMEngine)
            engine.index = mock_index
            engine.root_path = "/tmp/test"
            engine._client = MagicMock()
            engine._tracing_logger = MagicMock()
            engine._tracing_logger.access_log = []
            engine._rlm_bridge = MagicMock()
            engine._rlm_bridge.total_iterations = 1
            engine._tool_registry = {}
            engine._traced_index = MagicMock()
            engine._index_hash = "abc123"
            engine.user_logger = None
            engine.dev_logger = None
            engine.lsp = None
            engine.sandbox = "local"

            suggested = engine._reflect_on_tools([
                {"role": "user", "content": "test question"},
                {"role": "assistant", "content": "answer['ready'] = True"},
            ])

            assert len(suggested) == 1
            assert suggested[0]["name"] == "test_tool"
            mock_reflector.reflect.assert_called_once()

    def test_reflect_returns_empty_on_error(self):
        from codebase_agent.workflows.rlm_engine import RLMEngine

        engine = RLMEngine.__new__(RLMEngine)
        engine._client = MagicMock()

        with patch("codebase_agent.workflows.rlm_engine.ToolReflector") as mock_cls:
            mock_cls.return_value.reflect.side_effect = Exception("boom")
            result = engine._reflect_on_tools([])
            assert result == []


class TestRLMNamespaceNoRegisterTool:
    """Verify register_tool is removed from the RLM namespace."""

    def test_register_tool_not_in_namespace(self):
        from codebase_agent.workflows.rlm_engine import RLMEngine

        engine = RLMEngine.__new__(RLMEngine)
        engine.index = MagicMock()
        engine.root_path = "/tmp/test"
        engine.lsp = None
        engine._client = MagicMock()
        engine._tool_registry = {}
        engine._traced_index = MagicMock()
        engine._index_hash = "abc123"

        with patch.object(engine, "_inject_learned_tools") as mock_inject:
            def inject_and_add_register(ns):
                ns["register_tool"] = lambda: None
                ns.pop("register_tool", None)
            mock_inject.side_effect = inject_and_add_register

            namespace = engine._build_namespace()
            assert "register_tool" not in namespace
