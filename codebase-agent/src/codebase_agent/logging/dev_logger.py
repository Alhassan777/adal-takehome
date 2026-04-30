"""Developer-facing logger: full observability facade over all tracing subsystems."""

import logging
import os
import traceback

from ..models import IndexProfile
from ..tracing.cost_estimator import CostEstimator
from ..tracing.index_profiler import IndexProfiler
from ..tracing.token_tracker import TokenTracker
from ..tracing.tool_tracer import ToolTracer
from ..tracing.workflow_tracer import WorkflowTracer

logger = logging.getLogger("codebase_agent.dev")


class DevLogger:
    """Single entry point wiring together all tracing subsystems."""

    def __init__(self) -> None:
        self.token_tracker = TokenTracker()
        self.tool_tracer = ToolTracer()
        self.workflow_tracer = WorkflowTracer()
        self.index_profiler = IndexProfiler()
        self.cost_estimator = CostEstimator()

    def is_enabled(self) -> bool:
        return os.environ.get("CODEBASE_AGENT_DEV_LOG", "0") == "1"

    def on_tool_start(self, tool_name: str, args: dict) -> str:
        if not self.is_enabled():
            return ""
        trace_id = self.tool_tracer.start_call(tool_name, args)
        logger.debug(f"[TOOL START] {tool_name} args={args}")
        return trace_id

    def on_tool_end(
        self,
        trace_id: str,
        result: str,
        success: bool,
        error: str | None = None,
        subtask_id: str | None = None,
    ) -> None:
        if not self.is_enabled():
            return
        trace = self.tool_tracer.end_call(trace_id, result, success, error, subtask_id)
        self.token_tracker.record(trace.tool_name, str(trace.args), result, subtask_id)
        logger.debug(f"[TOOL END] {trace.tool_name} latency={trace.latency_ms:.1f}ms success={success}")

    def on_workflow_start(self, question: str, workflow_type: str) -> str:
        if not self.is_enabled():
            return ""
        wf_id = self.workflow_tracer.start_workflow(question, workflow_type)
        logger.debug(f"[WORKFLOW START] type={workflow_type} question={question[:100]}")
        return wf_id

    def on_subtask_start(self, workflow_id: str, name: str) -> str:
        if not self.is_enabled():
            return ""
        st_id = self.workflow_tracer.start_subtask(workflow_id, name)
        logger.debug(f"[SUBTASK START] {name}")
        return st_id

    def on_subtask_end(self, subtask_id: str, finding: dict) -> None:
        if not self.is_enabled():
            return
        self.workflow_tracer.end_subtask(subtask_id, finding)
        logger.debug(f"[SUBTASK END] {subtask_id}")

    def on_workflow_end(self, workflow_id: str, answer: dict) -> None:
        if not self.is_enabled():
            return
        self.workflow_tracer.end_workflow(workflow_id, answer)
        summary = self.token_tracker.workflow_summary()
        cost = self.cost_estimator.estimate(summary)
        logger.debug(
            f"[WORKFLOW END] tokens={summary.total_tokens} "
            f"cost=${cost.total_cost_usd:.6f}"
        )

    def on_index_built(self, profile: IndexProfile) -> None:
        if not self.is_enabled():
            return
        logger.debug(
            f"[INDEX] {profile.file_count} files, {profile.symbol_count} symbols "
            f"in {profile.total_duration_ms:.0f}ms (cache_hit={profile.cache_hit})"
        )

    def on_error(self, exc: Exception, context: str) -> None:
        if not self.is_enabled():
            return
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        logger.error(f"[ERROR] {context}: {exc}\n{''.join(tb)}")

    def export(self, workflow_id: str, repo_path: str | None = None, format: str = "json") -> str:
        from ..tracing.export import export_trace_json
        from ..config import INDEX_DIR, TRACE_DIR
        span = self.workflow_tracer.get_trace(workflow_id)
        if span is None:
            return ""
        if repo_path:
            output_dir = f"{repo_path}/{INDEX_DIR}/{TRACE_DIR}"
        else:
            output_dir = f"{INDEX_DIR}/{TRACE_DIR}"
        return export_trace_json(span, output_dir)
