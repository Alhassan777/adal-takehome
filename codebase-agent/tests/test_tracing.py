"""Tests for tracing.py -- multi-layer tracing for RLM mode."""

import pytest
from unittest.mock import MagicMock, patch

from codebase_agent.workflows.tracing import (
    DevLoggerAdapter,
    DevLoggerBridge,
    TracedRepoIndex,
    TracingLogger,
    wrap_tools_with_tracing,
)


class FakeIndex:
    """Minimal fake RepoIndex for testing."""

    def __init__(self):
        self.root_path = "/fake/repo"
        self.files = [{"path": "a.py"}, {"path": "b.py"}]
        self.symbols = [{"name": "foo"}, {"name": "bar"}]
        self.imports = [{"module": "os"}]
        self.test_map = {"a.py": ["test_a.py"]}
        self.name_reference_map = {"foo": ["a.py", "b.py"]}
        self.extra_attribute = "extra"


class TestTracingLogger:
    def test_base_logger_is_noop(self):
        logger = TracingLogger()
        trace_id = logger.on_tool_start("test", {})
        assert trace_id == ""
        logger.on_tool_end("", "result", True)
        logger.log_access("index.symbols", 10)
        logger.on_rlm_step("code", "output")


class TestDevLoggerAdapter:
    def test_delegates_to_dev_logger(self):
        mock_dev = MagicMock()
        mock_dev.on_tool_start.return_value = "trace-123"
        adapter = DevLoggerAdapter(mock_dev)

        trace_id = adapter.on_tool_start("search", {"query": "foo"})
        assert trace_id == "trace-123"
        mock_dev.on_tool_start.assert_called_once_with("search", {"query": "foo"})

        adapter.on_tool_end("trace-123", "result preview", True)
        mock_dev.on_tool_end.assert_called_once()

    def test_logs_access_to_internal_log(self):
        adapter = DevLoggerAdapter(None)
        adapter.log_access("index.symbols", count=50)
        adapter.log_access("index.files", count=10)

        assert len(adapter.access_log) == 2
        assert adapter.access_log[0] == {"attribute": "index.symbols", "count": 50}

    def test_handles_none_dev_logger(self):
        adapter = DevLoggerAdapter(None)
        trace_id = adapter.on_tool_start("test", {})
        assert trace_id == ""
        adapter.on_tool_end("", "result", True)


class TestWrapToolsWithTracing:
    def test_wraps_all_tools(self):
        registry = {
            "tool_a": lambda x=1: x * 2,
            "tool_b": lambda name="": f"hello {name}",
        }
        logger = TracingLogger()
        traced = wrap_tools_with_tracing(registry, logger)

        assert set(traced.keys()) == {"tool_a", "tool_b"}

    def test_traced_tool_returns_correct_result(self):
        registry = {"add": lambda a=0, b=0: a + b}
        logger = TracingLogger()
        traced = wrap_tools_with_tracing(registry, logger)

        assert traced["add"](a=3, b=4) == 7

    def test_traced_tool_logs_to_logger(self):
        registry = {"search": lambda query="": {"results": [query]}}
        mock_logger = MagicMock(spec=TracingLogger)
        mock_logger.on_tool_start.return_value = "t1"
        traced = wrap_tools_with_tracing(registry, mock_logger)

        result = traced["search"](query="foo")
        mock_logger.on_tool_start.assert_called_once_with("search", {"query": "foo"})
        mock_logger.on_tool_end.assert_called_once()
        assert result == {"results": ["foo"]}

    def test_traced_tool_logs_errors(self):
        def failing_tool(**kwargs):
            raise ValueError("boom")

        registry = {"bad": failing_tool}
        mock_logger = MagicMock(spec=TracingLogger)
        mock_logger.on_tool_start.return_value = "t1"
        traced = wrap_tools_with_tracing(registry, mock_logger)

        with pytest.raises(ValueError, match="boom"):
            traced["bad"]()

        mock_logger.on_tool_end.assert_called_once_with("t1", "", False, error="boom")


class TestTracedRepoIndex:
    def test_proxies_root_path(self):
        idx = FakeIndex()
        logger = DevLoggerAdapter(None)
        traced = TracedRepoIndex(idx, logger)

        assert traced.root_path == "/fake/repo"

    def test_logs_symbols_access(self):
        idx = FakeIndex()
        logger = DevLoggerAdapter(None)
        traced = TracedRepoIndex(idx, logger)

        symbols = traced.symbols
        assert symbols == idx.symbols
        assert len(logger.access_log) == 1
        assert logger.access_log[0]["attribute"] == "index.symbols"
        assert logger.access_log[0]["count"] == 2

    def test_logs_files_access(self):
        idx = FakeIndex()
        logger = DevLoggerAdapter(None)
        traced = TracedRepoIndex(idx, logger)

        files = traced.files
        assert files == idx.files
        assert logger.access_log[0]["attribute"] == "index.files"

    def test_logs_name_reference_map_access(self):
        idx = FakeIndex()
        logger = DevLoggerAdapter(None)
        traced = TracedRepoIndex(idx, logger)

        refs = traced.name_reference_map
        assert refs == idx.name_reference_map
        assert logger.access_log[0]["count"] == 1

    def test_fallthrough_getattr(self):
        idx = FakeIndex()
        logger = DevLoggerAdapter(None)
        traced = TracedRepoIndex(idx, logger)

        assert traced.extra_attribute == "extra"


class TestDevLoggerBridge:
    def test_records_iterations(self):
        bridge = DevLoggerBridge(dev_logger=None)

        bridge.on_iteration("x = 1", "")
        bridge.on_iteration("print(x)", "1")

        assert bridge.total_iterations == 2
        assert bridge.iterations[0]["code"] == "x = 1"
        assert bridge.iterations[1]["output"] == "1"

    def test_delegates_to_dev_logger(self):
        mock_dev = MagicMock()
        bridge = DevLoggerBridge(dev_logger=mock_dev)

        bridge.on_iteration("code", "output", sub_calls=["sub1"])
        mock_dev.on_rlm_step.assert_called_once_with(
            code="code", output="output", sub_calls=["sub1"]
        )

    def test_on_complete_noop(self):
        bridge = DevLoggerBridge(dev_logger=None)
        bridge.on_complete("final answer")
