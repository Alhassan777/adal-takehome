"""CLI entry point for the codebase navigation agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="codebase-agent",
    help="Navigate, search, inspect, and understand Python codebases.",
    no_args_is_help=True,
)
console = Console()


def _present_tool_suggestions(
    result: dict[str, Any],
    repo_path: str,
    user_logger: Any | None,
) -> None:
    """Present suggested tools to the user and handle approval interactively.

    Called after the RLM engine returns an answer that includes ``suggested_tools``.
    Each proposal is rendered via the UserLogger, and the user is prompted
    with [Y/n] per tool.  Approved tools go through the full
    LearnedToolRegistry validation pipeline (deterministic tests + critic).
    """
    suggestions = result.get("suggested_tools")
    if not suggestions:
        return

    from openai import OpenAI
    from ..workflows.learned_tools import LearnedToolRegistry

    client = OpenAI()
    cache_dir = Path(repo_path) / ".cache"
    registry = LearnedToolRegistry(cache_dir, client)

    if user_logger:
        user_logger.show_tool_suggestions_header(len(suggestions))

    for idx, proposal in enumerate(suggestions, 1):
        name = proposal.get("name", "unnamed")

        if user_logger:
            user_logger.show_tool_proposal(idx, proposal)

        try:
            choice = input(f"    Add to tool library? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n    [dim]Tool suggestions cancelled.[/dim]")
            return

        if choice in ("", "y", "yes"):
            console.print("    [dim]Validating...[/dim]")
            validation = registry.propose_tool(
                name=name,
                code=proposal.get("code", ""),
                description=proposal.get("description", ""),
                test_cases=proposal.get("test_cases", []),
            )
            if user_logger:
                user_logger.show_tool_promotion_result(name, validation)
            else:
                approved = validation.get("approved", False)
                feedback = validation.get("feedback", "")
                tag = "[green]Validated[/green]" if approved else "[yellow]Rejected[/yellow]"
                console.print(f"    {tag}: {feedback}")
        else:
            if user_logger:
                user_logger.show_tool_skipped(name)
            else:
                console.print("    [dim]Skipped.[/dim]")


@app.command()
def init(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Skip Pyright LSP startup"),
    no_summaries: bool = typer.Option(False, "--no-summaries", help="Skip NL summary generation"),
    watch: bool = typer.Option(False, "--watch", help="Watch for file changes after init"),
) -> None:
    """Initialize a session: index + summaries + LSP warmup (run at session start)."""
    from ..core.session import SessionConfig, init_session

    config = SessionConfig(
        use_lsp=not no_lsp,
        use_summaries=not no_summaries,
        watch=watch,
    )
    session = init_session(repo_path, config=config)

    console.print(f"[green]Session initialized:[/green]")
    console.print(f"  Files indexed:    {len(session.index.files)}")
    console.print(f"  Symbols parsed:   {len(session.index.symbols)}")
    console.print(f"  Summaries built:  {'yes' if session.summaries_built else 'skipped'}")
    console.print(f"  LSP (Pyright):    {'running' if session.lsp and session.lsp.is_running else 'disabled'}")

    if watch:
        console.print("\n[dim]Watching for changes... (Ctrl+C to stop)[/dim]")
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            session.shutdown()


@app.command()
def index(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    watch: bool = typer.Option(False, "--watch", help="Watch for file changes and re-index incrementally"),
) -> None:
    """Build or update the codebase index (without summaries or LSP)."""
    from ..core.session import SessionConfig, init_session

    config = SessionConfig(use_lsp=False, use_summaries=False, watch=watch)
    session = init_session(repo_path, config=config)
    console.print(f"[green]Indexed {len(session.index.files)} files, {len(session.index.symbols)} symbols.[/green]")

    if watch:
        console.print("[dim]Watching for changes... (Ctrl+C to stop)[/dim]")
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


@app.command(name="map")
def repo_map(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    depth: int = typer.Option(2, "--depth", "-d", help="Max directory depth"),
    with_summaries: bool = typer.Option(False, "--with-summaries", help="Include NL summaries"),
) -> None:
    """Display a hierarchical map of the repository."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import repo_map as do_repo_map

    idx = get_or_build_index(repo_path)
    result = do_repo_map(repo_path, idx, depth=depth, with_summaries=with_summaries)
    console.print_json(data=result)


@app.command()
def symbols(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    query: str = typer.Argument(..., help="Symbol name or pattern to search"),
) -> None:
    """Search for symbols in the codebase."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import search_symbols_tool

    idx = get_or_build_index(repo_path)
    result = search_symbols_tool(idx, query)
    console.print_json(data=result)


@app.command()
def definition(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    symbol_name: str = typer.Argument(..., help="Symbol to look up"),
    context_file: Optional[str] = typer.Option(None, "--context", "-c", help="File context for disambiguation"),
) -> None:
    """Get the definition of a symbol."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import get_definition

    idx = get_or_build_index(repo_path)
    result = get_definition(repo_path, idx, symbol_name, context_file=context_file)
    console.print_json(data=result)


@app.command()
def refs(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    symbol_name: str = typer.Argument(..., help="Symbol to find references for"),
) -> None:
    """Find all references to a symbol."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import find_references

    idx = get_or_build_index(repo_path)
    result = find_references(repo_path, idx, symbol_name)
    console.print_json(data=result)


@app.command()
def imports(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    file_path: str = typer.Argument(..., help="File to inspect imports for"),
) -> None:
    """Show imports for a file."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import get_imports

    idx = get_or_build_index(repo_path)
    result = get_imports(idx, file_path)
    console.print_json(data=result)


def _connect_mcp_servers(
    mcp_specs: list[str] | None,
) -> list:
    """Parse ``--mcp`` arguments and return connected MCPSession instances.

    Each *mcp_spec* has the form ``transport:url``, e.g.
    ``http:https://mcp.notion.com/mcp``.
    """
    if not mcp_specs:
        return []

    from ..mcp.session import MCPSession

    sessions = []
    for spec in mcp_specs:
        if ":" not in spec:
            console.print(f"[yellow]Invalid --mcp format (expected transport:url): {spec}[/yellow]")
            continue
        transport, url = spec.split(":", 1)
        if transport not in ("http", "sse"):
            console.print(f"[yellow]Unknown MCP transport '{transport}', expected http or sse[/yellow]")
            continue
        try:
            sess = MCPSession.connect(transport, url)
            n = len(sess.list_tools())
            console.print(f"[green]MCP connected:[/green] {url} ({n} tool(s))")
            sessions.append(sess)
        except Exception as exc:
            console.print(f"[red]MCP connection failed for {url}: {exc}[/red]")
    return sessions


@app.command()
def ask(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    question: str = typer.Argument(..., help="Question about the codebase (supports @file mentions)"),
    mode: str = typer.Option("adaptive", "--mode", "-m", help="Execution mode: adaptive or rlm"),
    sandbox: str = typer.Option("local", "--sandbox", help="Sandbox mode for RLM: local or docker"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", help="Quiet output (answer only)"),
    dev_log: bool = typer.Option(False, "--dev-log", help="Enable developer logging"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Skip Pyright LSP"),
    no_summaries: bool = typer.Option(False, "--no-summaries", help="Skip NL summaries"),
    mcp: Optional[list[str]] = typer.Option(None, "--mcp", help="Connect to MCP server (transport:url, e.g. http:https://mcp.notion.com/mcp)"),
) -> None:
    """Ask a question about the codebase (auto-inits session if needed)."""
    import os
    from ..config import ExecutionMode, SandboxMode, OPENAI_MODEL
    from ..workflows.engine import create_engine
    from .completer import parse_query
    from ..core.session import SessionConfig, get_or_init_session
    from ..logging.dev_logger import DevLogger
    from ..logging.user_logger import UserLogger

    execution_mode = ExecutionMode(mode)
    sandbox_mode = SandboxMode(sandbox)

    mcp_sessions = _connect_mcp_servers(mcp)

    dev_logger = None
    if dev_log:
        os.environ["CODEBASE_AGENT_DEV_LOG"] = "1"
        dev_logger = DevLogger(model=OPENAI_MODEL)

    config = SessionConfig(
        use_lsp=not no_lsp,
        use_summaries=not no_summaries,
        execution_mode=execution_mode,
        sandbox_mode=sandbox_mode,
    )
    profiler = dev_logger.index_profiler if dev_logger else None
    session = get_or_init_session(repo_path, config=config, profiler=profiler)

    if dev_logger and profiler and profiler.last_profile():
        dev_logger.on_index_built(profiler.last_profile())

    user_logger = None
    if not quiet:
        verbosity = "verbose" if verbose else "normal"
        user_logger = UserLogger(verbosity=verbosity, console=console)

    parsed = parse_query(question, session.mention_resolver)

    engine = create_engine(
        mode=execution_mode,
        index=session.index,
        root_path=session.root_path,
        lsp=session.lsp,
        sandbox=sandbox_mode,
        dev_logger=dev_logger,
        user_logger=user_logger,
        mcp_sessions=mcp_sessions or None,
    )
    result = engine.answer(parsed)

    if not quiet:
        wf = result.get("workflow_type", "unknown")
        console.print(f"\n[dim]Mode: {wf}[/dim]")

    console.print_json(data=result)

    if not quiet:
        _present_tool_suggestions(result, repo_path, user_logger)

    if dev_logger:
        wf_id = dev_logger.workflow_tracer.last_workflow_id()
        if wf_id:
            trace_path = dev_logger.export(wf_id, repo_path=repo_path)
            if trace_path:
                console.print(f"[dim]Trace saved: {trace_path}[/dim]")


@app.command()
def chat(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    mode: str = typer.Option("adaptive", "--mode", "-m", help="Execution mode: adaptive or rlm"),
    sandbox: str = typer.Option("local", "--sandbox", help="Sandbox mode for RLM: local or docker"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", help="Quiet output (answer only)"),
    dev_log: bool = typer.Option(False, "--dev-log", help="Enable developer logging"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Skip Pyright LSP"),
    no_summaries: bool = typer.Option(False, "--no-summaries", help="Skip NL summaries"),
    mcp: Optional[list[str]] = typer.Option(None, "--mcp", help="Connect to MCP server (transport:url, e.g. http:https://mcp.notion.com/mcp)"),
) -> None:
    """Interactive session: ask multiple questions in a long-lived REPL."""
    import os
    from prompt_toolkit import PromptSession
    from ..config import ExecutionMode, SandboxMode, OPENAI_MODEL
    from ..workflows.engine import create_engine
    from .completer import AtMentionCompleter, parse_query
    from ..core.session import SessionConfig, get_or_init_session
    from ..logging.dev_logger import DevLogger
    from ..logging.user_logger import UserLogger

    execution_mode = ExecutionMode(mode)
    sandbox_mode = SandboxMode(sandbox)

    mcp_sessions = _connect_mcp_servers(mcp)

    session_dev_logger = None
    if dev_log:
        os.environ["CODEBASE_AGENT_DEV_LOG"] = "1"
        session_dev_logger = DevLogger(model=OPENAI_MODEL)

    config = SessionConfig(
        use_lsp=not no_lsp,
        use_summaries=not no_summaries,
        watch=True,
        execution_mode=execution_mode,
        sandbox_mode=sandbox_mode,
    )
    profiler = session_dev_logger.index_profiler if session_dev_logger else None
    session = get_or_init_session(repo_path, config=config, profiler=profiler)

    if session_dev_logger and profiler and profiler.last_profile():
        session_dev_logger.on_index_built(profiler.last_profile())

    completer = AtMentionCompleter(session.mention_resolver)
    prompt_session: PromptSession = PromptSession(completer=completer)

    console.print(f"[green]Session ready.[/green]")
    console.print(f"  Files indexed:  {len(session.index.files)}")
    console.print(f"  Symbols parsed: {len(session.index.symbols)}")
    if mcp_sessions:
        total_mcp_tools = sum(len(s.list_tools()) for s in mcp_sessions)
        console.print(f"  MCP servers:    {len(mcp_sessions)} ({total_mcp_tools} remote tool(s))")
    console.print("[dim]Type your questions. Use @filename for file mentions. /exit to quit.[/dim]\n")

    while True:
        try:
            question = prompt_session.prompt("ask> ")
        except (EOFError, KeyboardInterrupt):
            break

        stripped = question.strip()
        if stripped.lower() in ("/exit", "/quit"):
            break
        if not stripped:
            continue

        user_logger = None
        if not quiet:
            verbosity = "verbose" if verbose else "normal"
            user_logger = UserLogger(verbosity=verbosity, console=console)

        parsed = parse_query(question, session.mention_resolver)

        engine = create_engine(
            mode=execution_mode,
            index=session.index,
            root_path=session.root_path,
            lsp=session.lsp,
            sandbox=sandbox_mode,
            dev_logger=session_dev_logger,
            user_logger=user_logger,
            mcp_sessions=mcp_sessions or None,
        )
        result = engine.answer(parsed)

        if not quiet:
            wf = result.get("workflow_type", "unknown")
            console.print(f"\n[dim]Mode: {wf}[/dim]")

        console.print_json(data=result)

        if not quiet:
            _present_tool_suggestions(result, repo_path, user_logger)

        if session_dev_logger:
            wf_id = session_dev_logger.workflow_tracer.last_workflow_id()
            if wf_id:
                trace_path = session_dev_logger.export(wf_id, repo_path=repo_path)
                if trace_path:
                    console.print(f"[dim]Trace saved: {trace_path}[/dim]")

        console.print()

    if session_dev_logger:
        session_total = session_dev_logger.token_tracker.session_summary()
        cost = session_dev_logger.cost_estimator.estimate(session_total)
        console.print(
            f"[dim]Session totals: {session_total.total_tokens} tokens, "
            f"est. cost ${cost.total_cost_usd:.4f}[/dim]"
        )

    session.shutdown()
    console.print("[dim]Session closed.[/dim]")


@app.command()
def workflows() -> None:
    """List all supported agent workflows."""
    from ..workflows.types import TIER_MAP, WorkflowType
    from ..workflows.playbooks import PLAYBOOKS

    from rich.table import Table

    table = Table(title="Supported Agent Workflows")
    table.add_column("Tier", style="bold", width=5)
    table.add_column("Workflow", style="cyan")
    table.add_column("Trigger", style="dim")
    table.add_column("Budget", justify="right")

    for tier in range(1, 7):
        tier_types = [wt for wt, t in TIER_MAP.items() if t == tier]
        for wt in tier_types:
            pb = PLAYBOOKS.get(wt)
            if pb:
                table.add_row(
                    str(tier),
                    wt.value,
                    pb.trigger_description[:60],
                    str(pb.max_tool_rounds),
                )

    console.print(table)


@app.command()
def summarize(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    llm_summaries: bool = typer.Option(False, "--llm-summaries", help="Use LLM for richer summaries"),
) -> None:
    """Generate natural-language summaries for all files."""
    from ..core.session import SessionConfig, get_or_init_session
    from ..intelligence.summarizer import build_summaries

    config = SessionConfig(use_lsp=False, use_summaries=False)
    session = get_or_init_session(repo_path, config=config)
    summaries = build_summaries(session.index, session.root_path, use_llm=llm_summaries)
    console.print(f"[green]Generated summaries for {len(summaries)} files.[/green]")


@app.command()
def summary(
    repo_path: str = typer.Argument(..., help="Path to the repository root"),
    file_path: str = typer.Argument(..., help="File to show summary for"),
) -> None:
    """Show the summary for a specific file."""
    from ..core.indexer import get_or_build_index
    from ..intelligence.tools import get_file_summary

    idx = get_or_build_index(repo_path)
    result = get_file_summary(idx, repo_path, file_path)
    console.print_json(data=result)


@app.command()
def trace(
    repo_path: str = typer.Argument(".", help="Path to the repository root (for locating .cache/traces/)"),
    last: bool = typer.Option(False, "--last", help="Show the last workflow trace"),
    session: bool = typer.Option(False, "--session", help="Show all traces from this session"),
) -> None:
    """View developer traces."""
    from ..tracing.export import export_last_trace, export_session_traces

    if last:
        export_last_trace(console, repo_path)
    elif session:
        export_session_traces(console, repo_path)
    else:
        console.print("[yellow]Use --last or --session to view traces.[/yellow]")


if __name__ == "__main__":
    app()
