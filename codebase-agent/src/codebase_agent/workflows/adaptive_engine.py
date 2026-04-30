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
from .tool_schemas import build_openai_tool_schemas
from .query_context import build_user_message


SYSTEM_PROMPT = """You are a codebase navigation agent. Your job is to answer questions about a Python repository by calling the provided tools.

Strategy:
1. Start with coarse exploration (search_summaries, search_symbols_tool) to find relevant files.
2. Narrow down using get_file_summary or get_definition for specific symbols.
3. Read exact code spans with read_snippet when you need implementation details.
4. Use find_references, trace_module, or impact_analysis for relationship questions.

Always ground your answer in specific file paths and line numbers. When you have enough information, provide a complete answer."""


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
        self._tool_registry = self._build_tool_registry()
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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        tool_calls_made = []
        relevant_files: set[str] = {f.path for f in parsed_query.mentioned_files}
        relevant_symbols: set[str] = set()

        for round_num in range(MAX_ADAPTIVE_ROUNDS):
            response = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=self._tool_schemas,
                tool_choice="auto",
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                final_text = choice.message.content or ""
                break

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                result = self._execute_tool(fn_name, fn_args, round_num, tool_calls_made)

                self._extract_refs(result, relevant_files, relevant_symbols)

                messages.append(choice.message.model_dump())
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

    def _execute_tool(self, name: str, args: dict, round_num: int, records: list) -> Any:
        """Execute a tool and record the call."""
        tool_fn = self._tool_registry.get(name)
        if not tool_fn:
            return {"error": f"Unknown tool: {name}"}

        trace_id = ""
        if self.dev_logger:
            trace_id = self.dev_logger.on_tool_start(name, args)

        if self.user_logger:
            budget = MAX_ADAPTIVE_ROUNDS
            self.user_logger.start_subtask(
                round_num + 1, budget,
                f"{name}({', '.join(f'{k}={v!r}' for k, v in list(args.items())[:2])})"
            )

        try:
            result = tool_fn(**args)
            records.append({"tool": name, "args": args, "success": True})

            if self.dev_logger and trace_id:
                self.dev_logger.on_tool_end(trace_id, str(result)[:2000], True)
            if self.user_logger:
                self.user_logger.subtask_result(self._preview(result))

            return result
        except Exception as e:
            records.append({"tool": name, "args": args, "success": False, "error": str(e)})

            if self.dev_logger and trace_id:
                self.dev_logger.on_tool_end(trace_id, "", False, error=str(e))
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

        summary = UserSummary(
            question_type="adaptive",
            files_analyzed=len(files_list),
            symbols_found=len(symbols_list),
            tools_called=len(tool_calls_made),
            duration_seconds=duration,
            confidence="high" if files_list else "medium",
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

    def _build_tool_registry(self) -> dict[str, Any]:
        from ..intelligence.tools import (
            find_references,
            find_tests,
            get_call_graph,
            get_definition,
            get_directory_summary,
            get_file_summary,
            get_imports,
            impact_analysis,
            list_tree,
            read_snippet,
            repo_map,
            search_summaries,
            search_symbols_tool,
            search_text_tool,
            trace_module,
        )

        root = self.root_path
        idx = self.index
        lsp = self.lsp

        return {
            "search_symbols_tool": lambda query="", **kw: search_symbols_tool(idx, query),
            "search_text_tool": lambda query="", file_glob="*.py", **kw: search_text_tool(root, query, file_glob),
            "get_definition": lambda symbol_name="", context_file=None, **kw: get_definition(root, idx, symbol_name, context_file, lsp=lsp),
            "find_references": lambda symbol_name="", **kw: find_references(root, idx, symbol_name, lsp=lsp),
            "read_snippet": lambda file_path="", start_line=1, end_line=50, **kw: read_snippet(root, file_path, start_line, end_line),
            "get_imports": lambda file_path="", **kw: get_imports(idx, file_path),
            "trace_module": lambda file_path="", **kw: trace_module(root, idx, file_path),
            "get_call_graph": lambda symbol_name="", **kw: get_call_graph(root, idx, symbol_name),
            "find_tests": lambda file_or_symbol="", **kw: find_tests(idx, file_or_symbol),
            "impact_analysis": lambda symbol_name="", **kw: impact_analysis(root, idx, symbol_name),
            "get_file_summary": lambda file_path="", **kw: get_file_summary(idx, root, file_path),
            "search_summaries": lambda query="", **kw: search_summaries(idx, root, query),
            "get_directory_summary": lambda dir_path="", **kw: get_directory_summary(idx, root, dir_path),
            "list_tree": lambda **kw: list_tree(root, idx),
            "repo_map": lambda depth=2, **kw: repo_map(root, idx, depth=depth),
        }
