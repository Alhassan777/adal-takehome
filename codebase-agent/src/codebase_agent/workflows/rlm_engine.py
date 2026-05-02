"""Option B: RLM Engine -- wraps the official rlms library with our tool registry.

The agent writes arbitrary Python in a REPL sandbox. It has access to:
- tools.* (our 15 pre-built tools, instrumented with tracing)
- learned_* (previously synthesized tools)
- index (TracedRepoIndex proxy for direct programmatic access)
- sub_call / batch_sub_call (delegate to worker LLMs)
- Standard Python (re, pathlib, collections, json, ast, etc.)

After answering, a ToolReflector reviews the conversation and may suggest
new reusable tools for the user to approve via the CLI.
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
from .tool_reflector import ToolReflector
from .tracing import DevLoggerAdapter, DevLoggerBridge, TracedRepoIndex, wrap_tools_with_tracing


RLM_SYSTEM_PROMPT = """You are a codebase navigation agent with access to a Python REPL.

Your goal: answer the user's question about their codebase by writing Python code.

CRITICAL OUTPUT CONTRACT:
- Output ONLY executable Python code.
- Do NOT write prose, explanations, apologies, or markdown.
- Do NOT wrap code in ``` fences.
- Every assistant response is passed directly to exec().
- If you need to inspect something, print it.
- When you know the answer, set:
  answer["content"] = "your final answer"
  answer["ready"] = True

Valid response example:
result = tools.search_symbols_tool(query="Order")
print(result)

Invalid response examples:
I will search for Order now.
```python
result = tools.search_symbols_tool(query="Order")
```

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

### Previously learned tools:
- Previously learned tools are available as `learned_*` functions.
- Learned tools can call other learned tools for composition.
- After you finish answering, the system will review your work and may suggest new reusable tools for the user to approve.

## Instructions:
1. Write Python code only to explore the codebase and answer the question.
2. When you have the complete answer, set: answer["content"] = "your answer" and answer["ready"] = True
3. Each response you write will be executed. You'll see the output before writing the next block.
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
        self._traced_index = TracedRepoIndex(index, self._tracing_logger)
        raw_registry = self._build_tool_registry(index_override=self._traced_index)
        self._tool_registry = wrap_tools_with_tracing(raw_registry, self._tracing_logger)
        self._index_hash = self._compute_index_hash()
        self._pending_sub_calls: list[dict[str, Any]] = []

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

            if self.dev_logger and response.usage:
                self.dev_logger.on_llm_usage(
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    model=OPENAI_MODEL,
                )

            raw_content = response.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": raw_content})
            code = self._extract_code(raw_content)

            if self.user_logger:
                self.user_logger.start_subtask(
                    iteration + 1, MAX_RLM_ITERATIONS,
                    f"REPL iteration {iteration + 1}"
                )
                if raw_content != code:
                    self.user_logger.subtask_result(f"[extracted code from markdown, {len(code)} chars]")
                if self.dev_logger:
                    self.user_logger.tool_preview("raw_llm_output", raw_content[:300])

            self._pending_sub_calls = []
            output = self._execute_in_repl(code, namespace)

            self._rlm_bridge.on_iteration(code, output, sub_calls=self._pending_sub_calls)

            if self.user_logger:
                self.user_logger.subtask_result(output[:200] if output else "no output")

            messages.append({"role": "user", "content": f"REPL output:\n{output[:3000]}"})

            if namespace.get("answer", {}).get("ready"):
                break

        duration = time.time() - start

        answer_dict = namespace.get("answer", {})
        final_answer = answer_dict.get("content") or (
            "Could not determine answer within iteration budget."
            if not answer_dict.get("ready")
            else ""
        )
        self._rlm_bridge.on_complete(final_answer)

        suggested_tools = self._reflect_on_tools(messages)

        result = self._build_answer(
            question=question,
            final_text=final_answer,
            duration=duration,
            suggested_tools=suggested_tools,
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
        """Inject previously learned tools into the namespace (read-only, no register_tool)."""
        try:
            from .learned_tools import LearnedToolRegistry
            cache_dir = Path(self.root_path) / ".cache"
            registry = LearnedToolRegistry(cache_dir, self._client)
            registry.inject_into_namespace(namespace, self._index_hash)
            namespace.pop("register_tool", None)
        except (ImportError, Exception):
            pass

    def _reflect_on_tools(self, messages: list[dict]) -> list[dict]:
        """Run post-answer reflection to suggest reusable tools."""
        try:
            reflector = ToolReflector(client=self._client)
            proposals = reflector.reflect(messages)
            return [p.to_dict() for p in proposals]
        except Exception:
            return []

    @staticmethod
    def _extract_code(content: str) -> str:
        """Strip markdown fences from LLM output so exec() gets clean Python."""
        import re
        # Match ```python ... ``` or ``` ... ``` blocks, extract the inner code
        fenced = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, re.DOTALL)
        if fenced:
            return "\n\n".join(fenced)
        # If the response is entirely wrapped in a single fence pair, strip it
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.split("\n")
            return "\n".join(lines[1:-1])

        lines = content.splitlines()
        python_start = re.compile(
            r"^\s*(answer|result|results|data|files|symbols|refs|imports|for |if |try:|from |import |print\(|tools\.|index\.|root_path|with |def |class )"
        )
        for i, line in enumerate(lines):
            if python_start.match(line):
                return "\n".join(lines[i:])
        return content

    def _execute_in_repl(self, code: str, namespace: dict) -> str:
        """Execute generated code in the REPL namespace.

        SECURITY NOTE: ``exec`` runs LLM-generated code with full local
        process privileges.  ``SandboxMode.LOCAL`` is intended for
        development / trusted-repo usage only.  Before exposing this to
        untrusted repos or multi-tenant workloads, implement
        ``SandboxMode.DOCKER`` (or another isolation layer) and gate on it
        here.
        """
        import io
        import contextlib

        if self.sandbox != "local" and self.sandbox.value != "local":
            raise RuntimeError(
                f"Unsupported sandbox mode '{self.sandbox}' reached _execute_in_repl. "
                "Only SandboxMode.LOCAL is currently supported."
            )

        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                try:
                    compiled_expr = compile(code, "<rlm>", "eval")
                except SyntaxError:
                    exec(code, namespace)
                else:
                    result = eval(compiled_expr, namespace)
                    if result is not None:
                        print(result)
            output = stdout_capture.getvalue()
        except Exception as e:
            output = f"Error: {type(e).__name__}: {e}"

        return output

    def _sub_call(self, prompt: str, context: str, depth: int = 0) -> str:
        """Delegate a focused question to a sub-model worker."""
        if depth >= MAX_SUB_MODEL_DEPTH:
            self._pending_sub_calls.append(
                {
                    "model": OPENAI_SUB_MODEL,
                    "depth": depth,
                    "status": "max_depth",
                    "prompt_preview": prompt[:200],
                    "context_chars": len(context),
                }
            )
            return "[max recursion depth reached]"

        response = self._client.chat.completions.create(
            model=OPENAI_SUB_MODEL,
            messages=[
                {"role": "system", "content": "You are a code analysis assistant. Answer concisely based on the provided context."},
                {"role": "user", "content": f"{prompt}\n\nContext:\n{context[:8000]}"},
            ],
        )

        if self.dev_logger and response.usage:
            self.dev_logger.on_llm_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                model=OPENAI_SUB_MODEL,
            )

        content = response.choices[0].message.content or ""
        self._pending_sub_calls.append(
            {
                "model": OPENAI_SUB_MODEL,
                "depth": depth,
                "status": "ok",
                "prompt_preview": prompt[:200],
                "context_chars": len(context),
                "response_chars": len(content),
            }
        )
        return content

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

    def _build_answer(
        self,
        question: str,
        final_text: str,
        duration: float,
        suggested_tools: list[dict] | None = None,
    ) -> dict:
        total_tokens = 0
        est_cost = 0.0
        if self.dev_logger:
            tok_summary = self.dev_logger.token_tracker.workflow_summary()
            total_tokens = tok_summary.total_tokens
            est_cost = self.dev_logger.cost_estimator.estimate(tok_summary).total_cost_usd

        summary = UserSummary(
            question_type="rlm",
            files_analyzed=0,
            symbols_found=0,
            tools_called=self._rlm_bridge.total_iterations,
            duration_seconds=duration,
            confidence="high" if final_text and "Could not" not in final_text else "medium",
            total_tokens=total_tokens,
            est_cost_usd=est_cost,
        )

        result = {
            "question": question,
            "workflow_type": "rlm",
            "answer": final_text,
            "rlm_iterations": self._rlm_bridge.total_iterations,
            "index_accesses": self._tracing_logger.access_log,
            "duration_seconds": duration,
            "summary": summary.model_dump(),
        }
        if suggested_tools:
            result["suggested_tools"] = suggested_tools
        return result

    def _build_tool_registry(self, index_override=None) -> dict[str, Any]:
        from .engine import build_tool_registry as _build_shared_tool_registry

        idx = index_override if index_override is not None else self.index
        return _build_shared_tool_registry(idx, self.root_path, lsp=self.lsp)


class _ToolNamespace:
    """Namespace object that allows `tools.search_symbols(...)` syntax in REPL."""

    def __init__(self, registry: dict[str, Any]):
        for name, fn in registry.items():
            setattr(self, name, fn)
