"""Multi-layer tracing for RLM mode (Option B).

Layer 1: Instrumented tool wrappers -- logs every tools.* call
Layer 2: TracedRepoIndex proxy -- logs direct index data access
Layer 3: DevLoggerBridge -- bridges rlms RLMLogger into our DevLogger
"""

from __future__ import annotations

from typing import Any

from ..models import RepoIndex


class TracingLogger:
    """Minimal interface for tracing backends (DevLogger or standalone)."""

    def on_tool_start(self, name: str, args: dict) -> str:
        return ""

    def on_tool_end(self, trace_id: str, result_preview: str, success: bool, error: str = "") -> None:
        pass

    def log_access(self, attribute: str, count: int = 0) -> None:
        pass

    def on_rlm_step(self, code: str, output: str, sub_calls: list | None = None) -> None:
        pass


class DevLoggerAdapter(TracingLogger):
    """Adapter that wraps a DevLogger instance into the TracingLogger interface."""

    def __init__(self, dev_logger):
        self._dev = dev_logger
        self._access_log: list[dict] = []

    def on_tool_start(self, name: str, args: dict) -> str:
        if self._dev:
            return self._dev.on_tool_start(name, args)
        return ""

    def on_tool_end(self, trace_id: str, result_preview: str, success: bool, error: str = "") -> None:
        if self._dev:
            self._dev.on_tool_end(trace_id, result_preview, success, error=error)

    def log_access(self, attribute: str, count: int = 0) -> None:
        self._access_log.append({"attribute": attribute, "count": count})

    def on_rlm_step(self, code: str, output: str, sub_calls: list | None = None) -> None:
        pass

    @property
    def access_log(self) -> list[dict]:
        return self._access_log


def wrap_tools_with_tracing(tool_registry: dict[str, Any], logger: TracingLogger) -> dict[str, Any]:
    """Layer 1: Wrap each tool function to log calls through the tracing logger."""
    traced = {}
    for name, fn in tool_registry.items():
        def _make_traced(tool_name: str, tool_fn):
            def traced_fn(*args, **kwargs):
                trace_id = logger.on_tool_start(tool_name, kwargs)
                try:
                    result = tool_fn(*args, **kwargs)
                    logger.on_tool_end(trace_id, str(result)[:2000], True)
                    return result
                except Exception as e:
                    logger.on_tool_end(trace_id, "", False, error=str(e))
                    raise
            traced_fn.__name__ = tool_name
            traced_fn.__doc__ = tool_fn.__doc__ if hasattr(tool_fn, "__doc__") else None
            return traced_fn
        traced[name] = _make_traced(name, fn)
    return traced


class TracedRepoIndex:
    """Layer 2: Proxy over RepoIndex that logs attribute access patterns."""

    def __init__(self, index: RepoIndex, logger: TracingLogger):
        object.__setattr__(self, "_index", index)
        object.__setattr__(self, "_logger", logger)

    @property
    def root_path(self) -> str:
        return self._index.root_path

    @property
    def files(self):
        self._logger.log_access("index.files", count=len(self._index.files))
        return self._index.files

    @property
    def symbols(self):
        self._logger.log_access("index.symbols", count=len(self._index.symbols))
        return self._index.symbols

    @property
    def imports(self):
        self._logger.log_access("index.imports", count=len(self._index.imports))
        return self._index.imports

    @property
    def test_map(self):
        self._logger.log_access("index.test_map", count=len(self._index.test_map))
        return self._index.test_map

    @property
    def name_reference_map(self):
        self._logger.log_access("index.name_reference_map", count=len(self._index.name_reference_map))
        return self._index.name_reference_map

    def __getattr__(self, name: str):
        return getattr(self._index, name)


class DevLoggerBridge:
    """Layer 3: Bridge between rlms RLMLogger events and our DevLogger.

    The rlms library calls these hooks during its execution loop.
    We forward them to DevLogger for unified trace output.
    """

    def __init__(self, dev_logger, log_dir: str | None = None):
        self._dev = dev_logger
        self._log_dir = log_dir
        self._iterations: list[dict] = []

    def on_iteration(self, code: str, output: str, sub_calls: list | None = None) -> None:
        """Called by rlms after each REPL iteration."""
        iteration = {
            "code": code,
            "output": output[:3000],
            "sub_calls": sub_calls or [],
            "iteration": len(self._iterations) + 1,
        }
        self._iterations.append(iteration)

        if self._dev:
            self._dev.on_rlm_step(
                code=code,
                output=output[:2000],
                sub_calls=sub_calls or [],
            )

    def on_complete(self, answer: str) -> None:
        """Called when RLM finishes."""
        pass

    @property
    def iterations(self) -> list[dict]:
        return self._iterations

    @property
    def total_iterations(self) -> int:
        return len(self._iterations)
