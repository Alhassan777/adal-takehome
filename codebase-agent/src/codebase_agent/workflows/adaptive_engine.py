"""Option A: Adaptive Engine -- LLM-driven tool selection via OpenAI function calling."""

from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI

from ..config import MAX_ADAPTIVE_ROUNDS, OPENAI_MODEL
from ..models import ParsedQuery, RepoIndex, UserSummary
from ..logging.dev_logger import DevLogger
from ..logging.user_logger import UserLogger
from .classifier import ClassificationResult, classify_question
from .playbooks import PLAYBOOKS, WorkflowPlaybook, get_playbook
from .tool_schemas import build_openai_tool_schemas
from .query_context import build_user_message
from .tracing import DevLoggerAdapter, TracedRepoIndex, wrap_tools_with_tracing


SYSTEM_PROMPT = """You are a codebase navigation agent. Your job is to answer questions about a Python repository by calling the provided tools.

Strategy:
1. Start with coarse exploration (search_summaries, search_symbols_tool) to find relevant files.
2. Narrow down using get_file_summary or get_definition for specific symbols.
3. Read exact code spans with read_snippet when you need implementation details.
4. Use find_references, trace_module, or impact_analysis for relationship questions.

Always ground your answer in specific file paths and line numbers. When you have enough information, provide a complete answer."""


def _build_strategy_hint(
    classification: ClassificationResult | None,
    playbook: WorkflowPlaybook | None,
) -> str:
    """Format a playbook as a strategy-hint system message.

    Returns an empty string when there is nothing useful to inject.
    """
    if classification is None or playbook is None:
        return ""

    lines = [
        f"Workflow hint ({playbook.workflow_type.value}, "
        f"confidence: {classification.confidence:.2f}):",
        f"Suggested tools: {', '.join(playbook.required_tools)}",
        "Strategy:",
    ]
    for i, step in enumerate(playbook.strategy_steps, 1):
        lines.append(f"  {i}. {step}")

    if playbook.failure_chains:
        lines.append("Fallbacks:")
        for trigger, action in playbook.failure_chains.items():
            lines.append(f"  - {trigger} -> {action}")

    if playbook.early_termination:
        lines.append(f"Early stop: {playbook.early_termination}")

    lines.append(
        "\nThis is a suggested strategy. Deviate from it if the question "
        "requires a different approach."
    )

    return "\n".join(lines)


class AdaptiveEngine:
    """LLM-driven agent loop using OpenAI function calling for tool selection."""

    def __init__(
        self,
        index: RepoIndex,
        root_path: str,
        *,
        lsp=None,
        dev_logger: DevLogger | None = None,
        user_logger: UserLogger | None = None,
    ):
        self.index = index
        self.root_path = root_path
        self.lsp = lsp
        self.dev_logger = dev_logger
        self.user_logger = user_logger
        self._tracing_logger = DevLoggerAdapter(dev_logger)
        self._traced_index = TracedRepoIndex(index, self._tracing_logger)
        raw_registry = self._build_tool_registry(index_override=self._traced_index)
        self._tool_registry = wrap_tools_with_tracing(raw_registry, self._tracing_logger)
        self._tool_schemas = build_openai_tool_schemas()
        self._client = OpenAI()

    def answer(self, parsed_query: ParsedQuery) -> dict:
        """Main entry point: run the adaptive tool-calling loop."""
        start = time.time()
        question = parsed_query.clean_query or parsed_query.raw_query
        user_message = build_user_message(parsed_query)

        if self.user_logger:
            self.user_logger.start_workflow(question, "adaptive")

        wf_id = ""
        if self.dev_logger:
            wf_id = self.dev_logger.on_workflow_start(question, "adaptive")

        classification = classify_question(question)
        playbook = get_playbook(classification.workflow) if classification else None
        strategy_hint = _build_strategy_hint(classification, playbook) if playbook else ""
        budget = playbook.max_tool_rounds if playbook else MAX_ADAPTIVE_ROUNDS

        if self.dev_logger and classification:
            self.dev_logger.on_workflow_start(
                f"[classifier] {classification.workflow.value} "
                f"(confidence={classification.confidence:.2f}, method={classification.method})",
                "classification",
            )

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if strategy_hint:
            messages.append({"role": "system", "content": strategy_hint})
        messages.append({"role": "user", "content": user_message})

        tool_calls_made = []
        relevant_files: set[str] = {f.path for f in parsed_query.mentioned_files}
        relevant_symbols: set[str] = set()

        for round_num in range(budget):
            response = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=self._tool_schemas,
                tool_choice="auto",
            )

            if self.dev_logger and response.usage:
                self.dev_logger.on_llm_usage(
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    model=OPENAI_MODEL,
                )

            choice = response.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                final_text = choice.message.content or ""
                break

            messages.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                result = self._execute_tool(fn_name, fn_args, round_num, tool_calls_made, budget=budget)

                self._extract_refs(result, relevant_files, relevant_symbols)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str)[:4000],
                })
        else:
            final_text = "Budget exhausted. Here is what I found so far based on the tool results."

        duration = time.time() - start

        answer = self._build_answer(
            question=question,
            final_text=final_text,
            tool_calls_made=tool_calls_made,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            duration=duration,
        )

        if self.dev_logger and wf_id:
            self.dev_logger.on_workflow_end(wf_id, answer)

        if self.user_logger:
            self.user_logger.end_workflow(UserSummary(**answer["summary"]))

        return answer

    def _execute_tool(self, name: str, args: dict, round_num: int, records: list, *, budget: int = MAX_ADAPTIVE_ROUNDS) -> Any:
        """Execute a tool and record the call."""
        tool_fn = self._tool_registry.get(name)
        if not tool_fn:
            return {"error": f"Unknown tool: {name}"}

        if self.user_logger:
            self.user_logger.start_subtask(
                round_num + 1, budget,
                f"{name}({', '.join(f'{k}={v!r}' for k, v in list(args.items())[:2])})"
            )

        try:
            result = tool_fn(**args)
            records.append({"tool": name, "args": args, "success": True})

            if self.user_logger:
                self.user_logger.subtask_result(self._preview(result))

            return result
        except Exception as e:
            records.append({"tool": name, "args": args, "success": False, "error": str(e)})

            if self.user_logger:
                self.user_logger.subtask_result(f"[failed] {e}")

            return {"error": str(e)}

    def _preview(self, output: Any) -> str:
        if output is None:
            return "no result"
        if isinstance(output, dict):
            count = output.get("count", output.get("total_files"))
            if count is not None:
                return f"{count} results"
            if output.get("found") is True:
                return f"found: {output.get('symbol', output.get('file', ''))}"
            if output.get("found") is False:
                return "not found"
        if isinstance(output, list):
            return f"{len(output)} items"
        return str(output)[:80]

    def _extract_refs(self, result: Any, files: set, symbols: set):
        if not isinstance(result, dict):
            return
        for key, val in result.items():
            if key in ("file", "file_path", "source_file") and isinstance(val, str) and val:
                files.add(val)
            if key in ("symbol", "qualified_name", "name") and isinstance(val, str) and val:
                symbols.add(val)
            if key == "reference_files" and isinstance(val, list):
                files.update(f for f in val if isinstance(f, str))
            if isinstance(val, dict):
                self._extract_refs(val, files, symbols)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        self._extract_refs(item, files, symbols)

    def _build_answer(self, question, final_text, tool_calls_made, relevant_files, relevant_symbols, duration):
        files_list = sorted(relevant_files - {""})[:15]
        symbols_list = sorted(relevant_symbols - {""})[:15]

        total_tokens = 0
        est_cost = 0.0
        if self.dev_logger:
            tok_summary = self.dev_logger.token_tracker.workflow_summary()
            total_tokens = tok_summary.total_tokens
            est_cost = self.dev_logger.cost_estimator.estimate(tok_summary).total_cost_usd

        summary = UserSummary(
            question_type="adaptive",
            files_analyzed=len(files_list),
            symbols_found=len(symbols_list),
            tools_called=len(tool_calls_made),
            duration_seconds=duration,
            confidence="high" if files_list else "medium",
            total_tokens=total_tokens,
            est_cost_usd=est_cost,
        )

        return {
            "question": question,
            "workflow_type": "adaptive",
            "answer": final_text,
            "relevant_files": files_list,
            "relevant_symbols": symbols_list,
            "tool_calls_made": len(tool_calls_made),
            "tool_call_details": tool_calls_made,
            "duration_seconds": duration,
            "summary": summary.model_dump(),
        }

    def _build_tool_registry(self, index_override=None) -> dict[str, Any]:
        from .engine import build_tool_registry as _build_shared_tool_registry

        idx = index_override if index_override is not None else self.index
        return _build_shared_tool_registry(idx, self.root_path, lsp=self.lsp)
