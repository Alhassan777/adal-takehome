"""Option B: RLM Engine -- wraps the official rlms library with our tool registry.

The agent writes arbitrary Python in a REPL sandbox. It has access to:
- tools.* (our 15 pre-built tools, instrumented with tracing)
- learned_* (previously synthesized tools)
- index (TracedRepoIndex proxy for direct programmatic access)
- sub_call / batch_sub_call (delegate to worker LLMs)
- register_tool (synthesize new reusable tools)
- Standard Python (re, pathlib, collections, json, ast, etc.)
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from ..config import (
    MAX_RLM_ITERATIONS,
    MAX_SUB_MODEL_DEPTH,
    OPENAI_MODEL,
    OPENAI_SUB_MODEL,
    SandboxMode,
)
from ..models import ParsedQuery, RepoIndex, UserSummary
from ..logging.dev_logger import DevLogger
from ..logging.user_logger import UserLogger
from .tool_schemas import build_tool_signatures_text
from .query_context import build_user_message
from .tracing import DevLoggerAdapter, DevLoggerBridge, TracedRepoIndex, wrap_tools_with_tracing


RLM_SYSTEM_PROMPT = """You are a codebase navigation agent with access to a Python REPL.

Your goal: answer the user's question about their codebase by writing Python code.

## Available in your REPL namespace:

### Pre-built tools (convenience functions, all logged):
{tool_signatures}

### Direct data access (for custom queries the tools can't express):
- `index.files` -- list of FileRecord(path, size, language)
- `index.symbols` -- list of SymbolRecord(name, qualified_name, kind, file_path, line_start, line_end, signature, docstring)
- `index.imports` -- list of ImportRecord(file_path, module, imported_name, alias)
- `index.name_reference_map` -- dict[symbol_name, list[file_paths]] for O(1) reference lookup
- `index.test_map` -- dict[source_file, list[test_files]]
- `root_path` -- absolute path to the repo root

### Sub-model delegation (for parallel analysis):
- `sub_call(prompt, context)` -- send a focused prompt + context to a worker LLM, returns string
- `batch_sub_call(tasks)` -- parallel execution; tasks = list of {{prompt, context}} dicts

### Skill synthesis (create reusable tools for future sessions):
- `register_tool(name, code, description, test_cases)` -- propose a new tool (validated before promotion)
- Previously learned tools are available as `learned_*` functions.
- Learned tools can call other learned tools for composition.

## Instructions:
1. Write Python code to explore the codebase and answer the question.
2. When you have the complete answer, set: answer["content"] = "your answer" and answer["ready"] = True
3. Each code block you write will be executed. You'll see the output before writing the next block.
4. Use tools.* for common operations. Write custom code for anything tools can't express.
5. Use sub_call/batch_sub_call to delegate analysis of large code chunks to worker LLMs.
"""


class RLMEngine:
    """Full RLM engine wrapping the rlms library with instrumented tool access."""

    def __init__(
        self,
        index: RepoIndex,
        root_path: str,
        *,
        lsp=None,
        sandbox: SandboxMode = SandboxMode.LOCAL,
        dev_logger: DevLogger | None = None,
        user_logger: UserLogger | None = None,
    ):
        self.index = index
        self.root_path = root_path
        self.lsp = lsp
        self.sandbox = sandbox
        if self.sandbox == SandboxMode.DOCKER:
            raise NotImplementedError(
                "RLM docker sandbox execution is not implemented yet. "
                "Use --sandbox local for development, or add an isolated Docker executor before enabling this mode."
            )
        self.dev_logger = dev_logger
        self.user_logger = user_logger
        self._client = OpenAI()
        self._tracing_logger = DevLoggerAdapter(dev_logger)
        self._rlm_bridge = DevLoggerBridge(dev_logger, log_dir=str(Path(root_path) / ".cache" / "rlm_traces"))

        raw_registry = self._build_tool_registry()
        self._tool_registry = wrap_tools_with_tracing(raw_registry, self._tracing_logger)
        self._traced_index = TracedRepoIndex(index, self._tracing_logger)
        self._index_hash = self._compute_index_hash()

    def answer(self, parsed_query: ParsedQuery) -> dict:
        """Main entry point: run the RLM REPL loop."""
        start = time.time()
        question = parsed_query.clean_query or parsed_query.raw_query
        user_message = build_user_message(parsed_query)

        if self.user_logger:
            self.user_logger.start_workflow(question, "rlm")

        wf_id = ""
        if self.dev_logger:
            wf_id = self.dev_logger.on_workflow_start(question, "rlm")

        namespace = self._build_namespace()
        system_prompt = RLM_SYSTEM_PROMPT.format(tool_signatures=build_tool_signatures_text())

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for iteration in range(MAX_RLM_ITERATIONS):
            response = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
            )

            code = response.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": code})

            if self.user_logger:
                self.user_logger.start_subtask(
                    iteration + 1, MAX_RLM_ITERATIONS,
                    f"REPL iteration {iteration + 1}"
                )

            output = self._execute_in_repl(code, namespace)

            self._rlm_bridge.on_iteration(code, output)

            if self.user_logger:
                self.user_logger.subtask_result(output[:200] if output else "no output")

            messages.append({"role": "user", "content": f"REPL output:\n{output[:3000]}"})

            if namespace.get("answer", {}).get("ready"):
                break

        duration = time.time() - start

        final_answer = namespace.get("answer", {}).get("content", "Could not determine answer within iteration budget.")

        result = self._build_answer(
            question=question,
            final_text=final_answer,
            duration=duration,
        )

        if self.dev_logger and wf_id:
            self.dev_logger.on_workflow_end(wf_id, result)

        if self.user_logger:
            self.user_logger.end_workflow(UserSummary(**result["summary"]))

        return result

    def _build_namespace(self) -> dict[str, Any]:
        """Build the REPL namespace with tools, index, and helpers."""
        import collections
        import json
        import re
        from pathlib import Path as _Path

        namespace: dict[str, Any] = {
            "tools": _ToolNamespace(self._tool_registry),
            "index": self._traced_index,
            "root_path": self.root_path,
            "answer": {"content": "", "ready": False},
            "sub_call": self._sub_call,
            "batch_sub_call": self._batch_sub_call,
            "re": re,
            "Path": _Path,
            "pathlib": __import__("pathlib"),
            "collections": collections,
            "json": json,
            "ast": __import__("ast"),
            "print": print,
        }

        self._inject_learned_tools(namespace)

        return namespace

    def _inject_learned_tools(self, namespace: dict) -> None:
        """Inject previously learned tools into the namespace."""
        try:
            from .learned_tools import LearnedToolRegistry
            cache_dir = Path(self.root_path) / ".cache"
            registry = LearnedToolRegistry(cache_dir, self._client)
            registry.inject_into_namespace(namespace, self._index_hash)
        except (ImportError, Exception):
            pass

    def _execute_in_repl(self, code: str, namespace: dict) -> str:
        """Execute generated code in the REPL namespace."""
        import io
        import contextlib

        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(code, namespace)
            output = stdout_capture.getvalue()
        except Exception as e:
            output = f"Error: {type(e).__name__}: {e}"

        return output

    def _sub_call(self, prompt: str, context: str, depth: int = 0) -> str:
        """Delegate a focused question to a sub-model worker."""
        if depth >= MAX_SUB_MODEL_DEPTH:
            return "[max recursion depth reached]"

        response = self._client.chat.completions.create(
            model=OPENAI_SUB_MODEL,
            messages=[
                {"role": "system", "content": "You are a code analysis assistant. Answer concisely based on the provided context."},
                {"role": "user", "content": f"{prompt}\n\nContext:\n{context[:8000]}"},
            ],
        )
        return response.choices[0].message.content or ""

    def _batch_sub_call(self, tasks: list[dict]) -> list[str]:
        """Execute multiple sub-model calls. Currently sequential; async planned."""
        results = []
        for task in tasks:
            result = self._sub_call(
                prompt=task.get("prompt", ""),
                context=task.get("context", ""),
            )
            results.append(result)
        return results

    def _compute_index_hash(self) -> str:
        """Compute a hash of the index for learned tool cache invalidation."""
        file_paths = sorted(f.path for f in self.index.files)
        content = "|".join(file_paths)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _build_answer(self, question: str, final_text: str, duration: float) -> dict:
        summary = UserSummary(
            question_type="rlm",
            files_analyzed=0,
            symbols_found=0,
            tools_called=self._rlm_bridge.total_iterations,
            duration_seconds=duration,
            confidence="high" if final_text and "Could not" not in final_text else "medium",
        )

        return {
            "question": question,
            "workflow_type": "rlm",
            "answer": final_text,
            "rlm_iterations": self._rlm_bridge.total_iterations,
            "index_accesses": self._tracing_logger.access_log,
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


class _ToolNamespace:
    """Namespace object that allows `tools.search_symbols(...)` syntax in REPL."""

    def __init__(self, registry: dict[str, Any]):
        for name, fn in registry.items():
            setattr(self, name, fn)
