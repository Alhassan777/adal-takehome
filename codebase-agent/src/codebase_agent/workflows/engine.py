"""Engine factory and shared tool registry for all execution modes.

The deterministic playbook executors have been removed. Both execution modes
(adaptive and rlm) are LLM-driven. Use create_engine() to instantiate the
appropriate engine based on configuration.
"""

from __future__ import annotations

from typing import Any

from ..config import ExecutionMode, SandboxMode
from ..models import RepoIndex
from ..logging.dev_logger import DevLogger
from ..logging.user_logger import UserLogger


def create_engine(
    mode: ExecutionMode,
    index: RepoIndex,
    root_path: str,
    *,
    lsp=None,
    sandbox: SandboxMode = SandboxMode.LOCAL,
    dev_logger: DevLogger | None = None,
    user_logger: UserLogger | None = None,
    mcp_sessions: list | None = None,
    **kwargs,
):
    """Factory: create the appropriate engine based on execution mode.

    Args:
        mode: ExecutionMode.ADAPTIVE or ExecutionMode.RLM
        index: Built RepoIndex for the codebase
        root_path: Absolute path to the repository root
        lsp: Optional LSP client for enhanced symbol resolution
        sandbox: Sandbox isolation level (only used by RLM mode)
        dev_logger: Developer trace logger
        user_logger: User-facing progress logger
        mcp_sessions: Optional list of connected MCPSession instances
    """
    if mode == ExecutionMode.ADAPTIVE:
        from .adaptive_engine import AdaptiveEngine

        return AdaptiveEngine(
            index,
            root_path,
            lsp=lsp,
            dev_logger=dev_logger,
            user_logger=user_logger,
            mcp_sessions=mcp_sessions,
        )
    elif mode == ExecutionMode.RLM:
        from .rlm_engine import RLMEngine

        return RLMEngine(
            index,
            root_path,
            lsp=lsp,
            sandbox=sandbox,
            dev_logger=dev_logger,
            user_logger=user_logger,
            mcp_sessions=mcp_sessions,
        )
    raise ValueError(f"Unknown execution mode: {mode}")


def build_tool_registry(index: RepoIndex, root_path: str, lsp=None) -> dict[str, Any]:
    """Build the shared tool registry used by all engine modes.

    Returns a dict mapping tool names to callable functions with bound args.
    """
    from ..intelligence.tools import (
        find_references,
        find_routes,
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

    return {
        "search_symbols_tool": lambda query="", **kw: search_symbols_tool(index, query),
        "search_text_tool": lambda query="", file_glob="*.py", **kw: search_text_tool(root_path, query, file_glob),
        "get_definition": lambda symbol_name="", context_file=None, context_position=None, **kw: get_definition(root_path, index, symbol_name, context_file, context_position, lsp=lsp),
        "find_references": lambda symbol_name="", **kw: find_references(root_path, index, symbol_name, lsp=lsp),
        "read_snippet": lambda file_path="", start_line=1, end_line=50, **kw: read_snippet(root_path, file_path, start_line, end_line),
        "get_imports": lambda file_path="", **kw: get_imports(index, file_path),
        "trace_module": lambda file_path="", **kw: trace_module(root_path, index, file_path),
        "get_call_graph": lambda symbol_name="", depth=1, **kw: get_call_graph(root_path, index, symbol_name, depth),
        "find_tests": lambda file_or_symbol="", **kw: find_tests(index, file_or_symbol),
        "impact_analysis": lambda symbol_name="", **kw: impact_analysis(root_path, index, symbol_name),
        "get_file_summary": lambda file_path="", **kw: get_file_summary(index, root_path, file_path),
        "search_summaries": lambda query="", **kw: search_summaries(index, root_path, query),
        "get_directory_summary": lambda dir_path="", **kw: get_directory_summary(index, root_path, dir_path),
        "list_tree": lambda **kw: list_tree(root_path, index),
        "repo_map": lambda depth=2, **kw: repo_map(root_path, index, depth=depth),
        "find_routes": lambda dir_path="", **kw: find_routes(root_path, index, dir_path),
    }
