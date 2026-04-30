"""OpenTelemetry-inspired span tree for full question-to-answer tracing."""

import uuid
from datetime import datetime, timezone

from ..models import Span


class WorkflowTracer:
    def __init__(self) -> None:
        self._workflows: dict[str, Span] = {}
        self._spans: dict[str, Span] = {}

    def start_workflow(self, question: str, workflow_type: str) -> str:
        span_id = str(uuid.uuid4())[:8]
        span = Span(
            span_id=span_id,
            name=f"workflow:{workflow_type}",
            start_time=datetime.now(timezone.utc),
            metadata={"question": question, "workflow_type": workflow_type},
        )
        self._workflows[span_id] = span
        self._spans[span_id] = span
        return span_id

    def start_subtask(self, workflow_id: str, subtask_name: str) -> str:
        span_id = str(uuid.uuid4())[:8]
        span = Span(
            span_id=span_id,
            parent_id=workflow_id,
            name=f"subtask:{subtask_name}",
            start_time=datetime.now(timezone.utc),
        )
        self._spans[span_id] = span

        parent = self._spans.get(workflow_id)
        if parent:
            parent.children.append(span)

        return span_id

    def end_subtask(self, subtask_id: str, finding: dict) -> None:
        span = self._spans.get(subtask_id)
        if span:
            span.end_time = datetime.now(timezone.utc)
            span.metadata["finding"] = str(finding)[:500]

    def end_workflow(self, workflow_id: str, answer: dict) -> None:
        span = self._spans.get(workflow_id)
        if span:
            span.end_time = datetime.now(timezone.utc)
            span.metadata["answer_keys"] = list(answer.keys()) if isinstance(answer, dict) else []

    def get_trace(self, workflow_id: str) -> Span | None:
        return self._workflows.get(workflow_id)

    def last_workflow_id(self) -> str | None:
        if self._workflows:
            return list(self._workflows.keys())[-1]
        return None
