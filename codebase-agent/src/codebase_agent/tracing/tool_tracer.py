"""Structured logging of every tool invocation."""

import time
import uuid
from datetime import datetime, timezone

from ..models import ToolTrace


class ToolTracer:
    def __init__(self) -> None:
        self._traces: dict[str, dict] = {}
        self._completed: list[ToolTrace] = []

    def start_call(self, tool_name: str, args: dict) -> str:
        trace_id = str(uuid.uuid4())[:8]
        self._traces[trace_id] = {
            "tool_name": tool_name,
            "args": {k: str(v)[:200] for k, v in args.items()},
            "start_time": time.perf_counter(),
            "timestamp": datetime.now(timezone.utc),
        }
        return trace_id

    def end_call(
        self,
        trace_id: str,
        result: str,
        success: bool,
        error: str | None = None,
        subtask_id: str | None = None,
    ) -> ToolTrace:
        info = self._traces.pop(trace_id, {})
        elapsed = (time.perf_counter() - info.get("start_time", 0)) * 1000

        trace = ToolTrace(
            tool_name=info.get("tool_name", "unknown"),
            args=info.get("args", {}),
            result_size_bytes=len(result.encode("utf-8")),
            result_token_estimate=len(result) // 4,
            latency_ms=elapsed,
            success=success,
            error=error,
            timestamp=info.get("timestamp"),
            subtask_id=subtask_id,
        )
        self._completed.append(trace)
        return trace

    def all_traces(self) -> list[ToolTrace]:
        return list(self._completed)

    def summary(self) -> dict:
        total = len(self._completed)
        failed = sum(1 for t in self._completed if not t.success)
        avg_latency = (
            sum(t.latency_ms for t in self._completed) / total if total > 0 else 0
        )
        return {
            "total_calls": total,
            "failed_calls": failed,
            "avg_latency_ms": round(avg_latency, 2),
        }
