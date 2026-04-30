"""Integration tests for both execution modes (adaptive + rlm)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from codebase_agent.config import ExecutionMode, SandboxMode
from codebase_agent.models import MentionedFile
from codebase_agent.workflows.engine import create_engine, build_tool_registry


class FakeIndex:
    """Minimal RepoIndex fake for engine tests."""

    def __init__(self):
        self.root_path = "/fake/repo"
        self.files = [
            MagicMock(path="src/main.py", size=100, language="python"),
            MagicMock(path="src/utils.py", size=50, language="python"),
        ]
        self.symbols = [
            MagicMock(name="main", qualified_name="src.main.main", kind="function", file_path="src/main.py"),
        ]
        self.imports = []
        self.test_map = {}
        self.name_reference_map = {"main": ["src/main.py"]}


class FakeParsedQuery:
    def __init__(self, query, mentioned_files=None):
        self.raw_query = query
        self.clean_query = query
        self.mentioned_files = mentioned_files or []


class TestCreateEngine:
    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_creates_adaptive_engine(self, mock_openai_cls):
        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        assert engine.__class__.__name__ == "AdaptiveEngine"
        mock_openai_cls.assert_called_once()

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_creates_rlm_engine(self, mock_openai_cls):
        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        assert engine.__class__.__name__ == "RLMEngine"
        mock_openai_cls.assert_called_once()

    def test_raises_for_invalid_mode(self):
        idx = FakeIndex()
        with pytest.raises(ValueError, match="Unknown execution mode"):
            create_engine("invalid", idx, "/fake/repo")

    def test_docker_sandbox_fails_fast_until_executor_exists(self):
        idx = FakeIndex()
        with pytest.raises(NotImplementedError, match="docker sandbox execution is not implemented"):
            create_engine(ExecutionMode.RLM, idx, "/fake/repo", sandbox=SandboxMode.DOCKER)


class TestBuildToolRegistry:
    def test_registry_has_all_15_tools(self):
        idx = FakeIndex()
        registry = build_tool_registry(idx, "/fake/repo")
        expected_tools = {
            "search_symbols_tool", "search_text_tool", "get_definition",
            "find_references", "read_snippet", "get_imports", "trace_module",
            "get_call_graph", "find_tests", "impact_analysis", "get_file_summary",
            "search_summaries", "get_directory_summary", "list_tree", "repo_map",
        }
        assert set(registry.keys()) == expected_tools

    def test_all_registry_entries_callable(self):
        idx = FakeIndex()
        registry = build_tool_registry(idx, "/fake/repo")
        for name, fn in registry.items():
            assert callable(fn), f"{name} is not callable"


class TestAdaptiveEngineAnswer:
    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_answer_with_direct_response(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.tool_calls = None
        mock_choice.message.content = "The main function is in src/main.py"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("What is the main function?"))

        assert result["workflow_type"] == "adaptive"
        assert "main" in result["answer"].lower()

    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_answer_includes_mentioned_file_context(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.tool_calls = None
        mock_choice.message.content = "Explained src/main.py"

        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        mentioned = [
            MentionedFile(
                path="src/main.py",
                content_preview="def main():\n    return 1",
                symbols=["main"],
            )
        ]
        result = engine.answer(FakeParsedQuery("Explain this", mentioned_files=mentioned))

        sent_messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert "Mentioned files supplied by the user" in sent_messages[1]["content"]
        assert "src/main.py" in sent_messages[1]["content"]
        assert "src/main.py" in result["relevant_files"]

    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_answer_with_tool_calls(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "search_symbols_tool"
        mock_tool_call.function.arguments = json.dumps({"query": "main"})

        mock_choice_1 = MagicMock()
        mock_choice_1.finish_reason = "tool_calls"
        mock_choice_1.message.tool_calls = [mock_tool_call]
        mock_choice_1.message.model_dump.return_value = {"role": "assistant", "content": None, "tool_calls": []}

        mock_choice_2 = MagicMock()
        mock_choice_2.finish_reason = "stop"
        mock_choice_2.message.tool_calls = None
        mock_choice_2.message.content = "Found the main function"

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[mock_choice_1]),
            MagicMock(choices=[mock_choice_2]),
        ]

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("Find main"))

        assert result["tool_calls_made"] >= 1
        assert result["answer"] == "Found the main function"


class TestRLMEngineAnswer:
    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_answer_with_simple_code(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        code_response = MagicMock()
        code_response.choices = [MagicMock()]
        code_response.choices[0].message.content = 'answer["content"] = "The repo has 2 files"\nanswer["ready"] = True'

        mock_client.chat.completions.create.return_value = code_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("How many files?"))

        assert result["workflow_type"] == "rlm"
        assert "2 files" in result["answer"]

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_rlm_answer_includes_mentioned_file_context(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        code_response = MagicMock()
        code_response.choices = [MagicMock()]
        code_response.choices[0].message.content = 'answer["content"] = "done"\nanswer["ready"] = True'
        mock_client.chat.completions.create.return_value = code_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        mentioned = [
            MentionedFile(
                path="src/utils.py",
                content_preview="def helper():\n    return 1",
                symbols=["helper"],
            )
        ]
        engine.answer(FakeParsedQuery("Explain this", mentioned_files=mentioned))

        sent_messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert "Mentioned files supplied by the user" in sent_messages[1]["content"]
        assert "src/utils.py" in sent_messages[1]["content"]

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_namespace_has_tools_and_index(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        namespace = engine._build_namespace()

        assert "tools" in namespace
        assert "index" in namespace
        assert "root_path" in namespace
        assert "sub_call" in namespace
        assert "batch_sub_call" in namespace
        assert "re" in namespace
        assert "Path" in namespace
        assert "json" in namespace
        assert "answer" in namespace

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_repl_executes_code_in_namespace(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        namespace = engine._build_namespace()

        output = engine._execute_in_repl("x = 42\nprint(x)", namespace)
        assert "42" in output
        assert namespace["x"] == 42

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_repl_handles_errors_gracefully(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        namespace = engine._build_namespace()

        output = engine._execute_in_repl("raise ValueError('test error')", namespace)
        assert "ValueError" in output
        assert "test error" in output


class TestRLMSubCalls:
    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_sub_call_uses_sub_model(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        sub_response = MagicMock()
        sub_response.choices = [MagicMock()]
        sub_response.choices[0].message.content = "Summary of the code"
        mock_client.chat.completions.create.return_value = sub_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        result = engine._sub_call("Summarize this", "def foo(): pass")

        assert result == "Summary of the code"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_sub_call_respects_depth_limit(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        result = engine._sub_call("test", "context", depth=10)

        assert "max recursion depth" in result
        mock_client.chat.completions.create.assert_not_called()

    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_batch_sub_call(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        sub_response = MagicMock()
        sub_response.choices = [MagicMock()]
        sub_response.choices[0].message.content = "result"
        mock_client.chat.completions.create.return_value = sub_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        tasks = [
            {"prompt": "task 1", "context": "ctx 1"},
            {"prompt": "task 2", "context": "ctx 2"},
        ]
        results = engine._batch_sub_call(tasks)

        assert len(results) == 2
        assert all(r == "result" for r in results)
