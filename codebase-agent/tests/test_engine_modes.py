"""Integration tests for both execution modes (adaptive + rlm)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from codebase_agent.config import ExecutionMode, SandboxMode, MAX_ADAPTIVE_ROUNDS, MAX_RLM_ITERATIONS
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


# ============================================================
# Regression: Adaptive budget exhaustion
# ============================================================


class TestAdaptiveBudgetExhaustion:
    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_budget_exhausted_returns_fallback_message(self, mock_openai_cls):
        """When every round returns tool_calls and never 'stop', budget text is returned."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_loop"
        mock_tool_call.function.name = "search_symbols_tool"
        mock_tool_call.function.arguments = json.dumps({"query": "x"})

        mock_choice = MagicMock()
        mock_choice.finish_reason = "tool_calls"
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_choice.message.content = None
        mock_choice.message.model_dump.return_value = {
            "role": "assistant", "content": None, "tool_calls": [],
        }

        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("Find something"))

        assert "Budget exhausted" in result["answer"]
        assert result["tool_calls_made"] == MAX_ADAPTIVE_ROUNDS
        assert mock_client.chat.completions.create.call_count == MAX_ADAPTIVE_ROUNDS


# ============================================================
# Regression: Adaptive multi-tool transcript structure
# ============================================================


class TestAdaptiveMultiToolTranscript:
    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_multi_tool_appends_one_assistant_then_n_tool_messages(self, mock_openai_cls):
        """When a single turn has 2+ tool calls, exactly one assistant message
        is appended followed by N tool-result messages."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tc1 = MagicMock()
        tc1.id = "call_a"
        tc1.function.name = "search_symbols_tool"
        tc1.function.arguments = json.dumps({"query": "a"})

        tc2 = MagicMock()
        tc2.id = "call_b"
        tc2.function.name = "list_tree"
        tc2.function.arguments = json.dumps({})

        assistant_dump = {"role": "assistant", "content": None, "tool_calls": ["tc1", "tc2"]}

        multi_choice = MagicMock()
        multi_choice.finish_reason = "tool_calls"
        multi_choice.message.tool_calls = [tc1, tc2]
        multi_choice.message.content = None
        multi_choice.message.model_dump.return_value = assistant_dump

        stop_choice = MagicMock()
        stop_choice.finish_reason = "stop"
        stop_choice.message.tool_calls = None
        stop_choice.message.content = "Done"

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[multi_choice]),
            MagicMock(choices=[stop_choice]),
        ]

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        engine.answer(FakeParsedQuery("multi tool test"))

        first_call_messages = mock_client.chat.completions.create.call_args_list[1][1]["messages"]
        roles_after_user = [m["role"] if isinstance(m, dict) else m.get("role") for m in first_call_messages[2:]]
        assert roles_after_user == ["assistant", "tool", "tool"]


# ============================================================
# Regression: Adaptive error branches
# ============================================================


class TestAdaptiveToolErrors:
    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_unknown_tool_returns_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tc = MagicMock()
        tc.id = "call_bad"
        tc.function.name = "nonexistent_tool"
        tc.function.arguments = json.dumps({})

        tool_choice = MagicMock()
        tool_choice.finish_reason = "tool_calls"
        tool_choice.message.tool_calls = [tc]
        tool_choice.message.content = None
        tool_choice.message.model_dump.return_value = {"role": "assistant", "content": None, "tool_calls": []}

        stop_choice = MagicMock()
        stop_choice.finish_reason = "stop"
        stop_choice.message.tool_calls = None
        stop_choice.message.content = "Final answer"

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[tool_choice]),
            MagicMock(choices=[stop_choice]),
        ]

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("test unknown"))

        tool_msg = mock_client.chat.completions.create.call_args_list[1][1]["messages"][-1]
        assert "Unknown tool" in tool_msg["content"]
        assert result["answer"] == "Final answer"

    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_malformed_json_args_defaults_to_empty(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tc = MagicMock()
        tc.id = "call_bad_json"
        tc.function.name = "search_symbols_tool"
        tc.function.arguments = "not valid json{{"

        tool_choice = MagicMock()
        tool_choice.finish_reason = "tool_calls"
        tool_choice.message.tool_calls = [tc]
        tool_choice.message.content = None
        tool_choice.message.model_dump.return_value = {"role": "assistant", "content": None, "tool_calls": []}

        stop_choice = MagicMock()
        stop_choice.finish_reason = "stop"
        stop_choice.message.tool_calls = None
        stop_choice.message.content = "done"

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[tool_choice]),
            MagicMock(choices=[stop_choice]),
        ]

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("bad json test"))

        assert result["tool_calls_made"] >= 1
        assert result["answer"] == "done"

    @patch("codebase_agent.workflows.adaptive_engine.OpenAI")
    def test_tool_exception_records_failure(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tc = MagicMock()
        tc.id = "call_err"
        tc.function.name = "search_symbols_tool"
        tc.function.arguments = json.dumps({"query": "x"})

        tool_choice = MagicMock()
        tool_choice.finish_reason = "tool_calls"
        tool_choice.message.tool_calls = [tc]
        tool_choice.message.content = None
        tool_choice.message.model_dump.return_value = {"role": "assistant", "content": None, "tool_calls": []}

        stop_choice = MagicMock()
        stop_choice.finish_reason = "stop"
        stop_choice.message.tool_calls = None
        stop_choice.message.content = "recovered"

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[tool_choice]),
            MagicMock(choices=[stop_choice]),
        ]

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.ADAPTIVE, idx, "/fake/repo")
        engine._tool_registry["search_symbols_tool"] = MagicMock(side_effect=RuntimeError("boom"))
        result = engine.answer(FakeParsedQuery("tool error test"))

        assert result["tool_call_details"][0]["success"] is False
        assert "boom" in result["tool_call_details"][0]["error"]
        assert result["answer"] == "recovered"


# ============================================================
# Regression: RLM no-ready fallback
# ============================================================


class TestRLMBudgetExhaustion:
    @patch("codebase_agent.workflows.rlm_engine.OpenAI")
    def test_no_ready_returns_fallback_answer(self, mock_openai_cls):
        """When the RLM loop runs all iterations without setting answer['ready'],
        a budget-exhaustion fallback string is returned."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        code_response = MagicMock()
        code_response.choices = [MagicMock()]
        code_response.choices[0].message.content = 'print("still thinking")'
        mock_client.chat.completions.create.return_value = code_response

        idx = FakeIndex()
        engine = create_engine(ExecutionMode.RLM, idx, "/fake/repo")
        result = engine.answer(FakeParsedQuery("unanswerable"))

        assert "Could not determine answer" in result["answer"]
        assert result["rlm_iterations"] == MAX_RLM_ITERATIONS
