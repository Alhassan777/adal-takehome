"""Post-answer tool reflection for RLM mode.

After the RLM agent finishes answering a question, this module sends a
lightweight LLM call to review the REPL conversation and propose reusable
tools that could be promoted to the learned tool library (with user approval).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from ..config import OPENAI_SUB_MODEL
from .tool_schemas import TOOL_DESCRIPTIONS


_REFLECTION_SYSTEM_TEMPLATE = """\
You are a tool-synthesis advisor for a codebase navigation agent.

You will receive the full conversation from an RLM session where the agent \
answered a user's question by writing Python code in a REPL. Your job is to \
review what the agent did and identify reusable tool functions worth saving \
for future sessions.

## Built-in tools (do NOT suggest duplicates of these):
{builtin_tools}

## Criteria for suggesting a tool:
1. **Pattern reuse**: The agent wrote custom logic (not just calling built-in tools) that solves a recurring pattern.
2. **Generalizability**: The tool would be useful across different codebases or different questions, not just this specific query.
3. **Non-redundancy**: The tool provides capability that the 15 built-in tools cannot express.
4. **Testability**: You can define simple test cases for the tool.

## Response format:
Return a JSON object with a single key "proposals" containing an array of \
tool proposals (0-3 max). If nothing is worth suggesting, return \
{{"proposals": []}}.

Each proposal must have:
- "name": snake_case function name
- "description": one-sentence description of what the tool does
- "code": complete Python function source (must define a function with the given name; \
may use `index`, `root_path`, `Path`, `re`, `json`, `ast`, `collections` from the REPL namespace)
- "test_cases": list of {{"input": {{kwargs}}, "expected_contains": "substring"}} dicts (at least 1)
- "rationale": 1-2 sentences explaining why this is worth saving

Only suggest tools when there is a clear, reusable pattern. It is perfectly \
fine to return zero proposals."""


@dataclass
class ToolProposal:
    """A single tool suggestion from the reflector."""

    name: str
    description: str
    code: str
    test_cases: list[dict[str, Any]]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "code": self.code,
            "test_cases": self.test_cases,
            "rationale": self.rationale,
        }


@dataclass
class ToolReflector:
    """Reflects on an RLM conversation to propose reusable tools."""

    client: OpenAI = field(default_factory=OpenAI)

    def reflect(self, messages: list[dict[str, str]]) -> list[ToolProposal]:
        """Analyze a completed RLM conversation and return tool proposals.

        Args:
            messages: The full message history from the RLM REPL loop
                      (system + user + assistant + REPL output messages).

        Returns:
            List of ToolProposal objects (0-3 items). Empty if nothing
            worth suggesting was found.
        """
        builtin_list = "\n".join(
            f"- tools.{name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()
        )
        system = _REFLECTION_SYSTEM_TEMPLATE.format(builtin_tools=builtin_list)

        conversation_text = self._summarize_conversation(messages)

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_SUB_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": conversation_text},
                ],
                response_format={"type": "json_object"},
            )
            raw = json.loads(response.choices[0].message.content or "{}")
            return self._parse_proposals(raw)
        except Exception:
            return []

    def _summarize_conversation(self, messages: list[dict[str, str]]) -> str:
        """Build a compact representation of the RLM conversation for the reflector."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            label = {"user": "USER", "assistant": "AGENT CODE"}.get(role, role.upper())
            parts.append(f"[{label}]\n{content[:2000]}")
        return "\n\n".join(parts)

    def _parse_proposals(self, raw: dict[str, Any]) -> list[ToolProposal]:
        """Parse and validate the LLM's JSON response into ToolProposal objects."""
        proposals_raw = raw.get("proposals", [])
        if not isinstance(proposals_raw, list):
            return []

        proposals: list[ToolProposal] = []
        for item in proposals_raw[:3]:
            if not isinstance(item, dict):
                continue

            name = item.get("name", "")
            code = item.get("code", "")
            description = item.get("description", "")
            test_cases = item.get("test_cases", [])
            rationale = item.get("rationale", "")

            if not all([name, code, description]):
                continue
            if not isinstance(test_cases, list) or len(test_cases) == 0:
                continue

            proposals.append(ToolProposal(
                name=name,
                description=description,
                code=code,
                test_cases=test_cases,
                rationale=rationale,
            ))

        return proposals
