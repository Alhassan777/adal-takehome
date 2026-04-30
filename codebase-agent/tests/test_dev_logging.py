"""Tests for developer logging subsystem."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.logging.dev_logger import DevLogger
from codebase_agent.tracing.token_tracker import TokenTracker
from codebase_agent.tracing.tool_tracer import ToolTracer
from codebase_agent.tracing.workflow_tracer import WorkflowTracer
from codebase_agent.tracing.cost_estimator import CostEstimator
from codebase_agent.models import TokenSummary


def test_token_tracker_accumulation():
    tracker = TokenTracker()
    tracker.record("search", "hello world query", "result data here", subtask_id="s1")
    tracker.record("definition", "another query", "more results", subtask_id="s1")

    summary = tracker.workflow_summary()
    assert summary.total_tokens > 0
    assert summary.call_count == 2
    assert "search" in summary.by_tool


def test_token_tracker_hotspots():
    tracker = TokenTracker()
    for _ in range(5):
        tracker.record("search", "x" * 100, "y" * 200)
    tracker.record("definition", "a" * 50, "b" * 50)

    hotspots = tracker.hotspots(top_n=5)
    assert len(hotspots) >= 1
    assert hotspots[0].tool_name == "search"
    assert hotspots[0].pct_of_total > 50


def test_tool_tracer_records_latency():
    tracer = ToolTracer()
    trace_id = tracer.start_call("search_text", {"query": "test"})
    trace = tracer.end_call(trace_id, "some result", success=True)
    assert trace.latency_ms >= 0
    assert trace.tool_name == "search_text"
    assert trace.success is True


def test_tool_tracer_summary():
    tracer = ToolTracer()
    t1 = tracer.start_call("a", {})
    tracer.end_call(t1, "r", True)
    t2 = tracer.start_call("b", {})
    tracer.end_call(t2, "r", False, error="fail")

    summary = tracer.summary()
    assert summary["total_calls"] == 2
    assert summary["failed_calls"] == 1


def test_workflow_tracer_span_tree():
    tracer = WorkflowTracer()
    wf_id = tracer.start_workflow("How does auth work?", "feature_explanation")
    st_id = tracer.start_subtask(wf_id, "search_symbols")
    tracer.end_subtask(st_id, {"found": 3})
    tracer.end_workflow(wf_id, {"answer": "..."})

    span = tracer.get_trace(wf_id)
    assert span is not None
    assert span.span_id == wf_id
    assert len(span.children) == 1
    assert span.children[0].name == "subtask:search_symbols"


def test_cost_estimator():
    estimator = CostEstimator(model="gpt-4o-mini")
    summary = TokenSummary(input_tokens=1000, output_tokens=500, total_tokens=1500, call_count=3)
    cost = estimator.estimate(summary)
    assert cost.total_cost_usd > 0
    assert cost.model == "gpt-4o-mini"


def test_dev_logger_disabled_is_noop():
    os.environ.pop("CODEBASE_AGENT_DEV_LOG", None)
    logger = DevLogger()
    assert not logger.is_enabled()
    trace_id = logger.on_tool_start("test", {"arg": "val"})
    assert trace_id == ""


def test_dev_logger_enabled():
    os.environ["CODEBASE_AGENT_DEV_LOG"] = "1"
    logger = DevLogger()
    assert logger.is_enabled()
    trace_id = logger.on_tool_start("test", {"arg": "val"})
    assert trace_id != ""
    logger.on_tool_end(trace_id, "result", success=True)
    os.environ.pop("CODEBASE_AGENT_DEV_LOG", None)
