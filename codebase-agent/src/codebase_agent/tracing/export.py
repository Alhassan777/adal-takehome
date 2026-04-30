"""Trace export: JSON files, rich console, CSV."""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import INDEX_DIR, TRACE_DIR
from ..models import Span


def _resolve_trace_dir(repo_path: str | None = None) -> Path:
    """Resolve the trace directory, anchored to a repo root if provided."""
    if repo_path:
        return Path(repo_path).resolve() / INDEX_DIR / TRACE_DIR
    return Path(INDEX_DIR) / TRACE_DIR


def export_trace_json(span: Span, output_dir: str) -> str:
    """Export a workflow trace to JSON."""
    path = Path(output_dir) / f"{span.span_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = span.model_dump(mode="python")
    path.write_text(json.dumps(data, indent=2, default=str))
    return str(path)


def export_last_trace(console: Console, repo_path: str | None = None) -> None:
    """Display the last trace from .cache/traces/."""
    trace_dir = _resolve_trace_dir(repo_path)
    if not trace_dir.exists():
        console.print("[yellow]No traces found.[/yellow]")
        return

    files = sorted(trace_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        console.print("[yellow]No traces found.[/yellow]")
        return

    data = json.loads(files[0].read_text())
    console.print(Panel(json.dumps(data, indent=2, default=str)[:2000], title="Last Trace"))


def export_session_traces(console: Console, repo_path: str | None = None) -> None:
    """Display all traces from this session."""
    trace_dir = _resolve_trace_dir(repo_path)
    if not trace_dir.exists():
        console.print("[yellow]No traces found.[/yellow]")
        return

    files = sorted(trace_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        console.print("[yellow]No traces found.[/yellow]")
        return

    table = Table(title="Session Traces")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Duration")

    for f in files[:20]:
        data = json.loads(f.read_text())
        table.add_row(
            data.get("span_id", ""),
            data.get("name", ""),
            str(data.get("metadata", {}).get("duration_ms", "")),
        )

    console.print(table)
