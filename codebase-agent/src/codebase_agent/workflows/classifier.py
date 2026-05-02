"""LLM-based workflow classifier using OPENAI_SUB_MODEL.

Sends the user question plus the full list of 23 workflow types (with trigger
descriptions pulled from playbooks.py) to a small model, which returns a
JSON classification.  Returns None on any failure so callers can fall back
gracefully to the generic prompt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from ..config import OPENAI_SUB_MODEL
from .types import WorkflowType

log = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "You are classifying a codebase navigation question into exactly one "
    "workflow type.  Choose the single best match from the list below.\n\n"
    "Respond with JSON only: "
    '{"workflow": "<workflow_value>", "confidence": <0.0-1.0>}'
)


@dataclass
class ClassificationResult:
    """Result of classifying a user question into a workflow type."""

    workflow: WorkflowType
    confidence: float
    method: str  # "llm"
    extracted_params: dict = field(default_factory=dict)


def _build_type_descriptions() -> str:
    """Build the workflow-type reference list from playbook trigger descriptions."""
    from .playbooks import PLAYBOOKS

    lines: list[str] = []
    for wtype, playbook in PLAYBOOKS.items():
        lines.append(f"- {wtype.value}: {playbook.trigger_description}")
    return "\n".join(lines)


def classify_question(
    question: str,
    mentioned_files: list | None = None,
    conversation_history: list | None = None,
) -> Optional[ClassificationResult]:
    """Classify a codebase question into a workflow type via LLM.

    Returns None if the classification call fails for any reason so the
    caller can fall back to the generic prompt and full round budget.
    """
    type_descriptions = _build_type_descriptions()
    user_prompt = f"Workflow types:\n{type_descriptions}\n\nQuestion: {question}"

    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=OPENAI_SUB_MODEL,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=64,
        )

        raw = response.choices[0].message.content or ""
        data = json.loads(raw)

        workflow_value = data["workflow"]
        confidence = float(data.get("confidence", 0.8))

        workflow = WorkflowType(workflow_value)

        return ClassificationResult(
            workflow=workflow,
            confidence=min(max(confidence, 0.0), 1.0),
            method="llm",
        )

    except Exception:
        log.debug("LLM classification failed, falling back to generic prompt", exc_info=True)
        return None
