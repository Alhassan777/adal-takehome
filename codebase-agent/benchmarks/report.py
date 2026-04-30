"""Report generation: aggregate benchmark results into markdown + JSON.

Usage:
    python -m benchmarks.report benchmarks/results/2026-04-30_22-00-00/
    python -m benchmarks.report --latest
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="report", help="Generate benchmark reports.")
console = Console()

RESULTS_DIR = Path(__file__).parent / "results"


def find_latest_run() -> Path | None:
    """Find the most recent results directory."""
    if not RESULTS_DIR.exists():
        return None
    runs = sorted(RESULTS_DIR.iterdir(), reverse=True)
    return runs[0] if runs else None


def load_metrics(run_dir: Path) -> dict[str, dict[str, dict]]:
    """Load all metrics files from a results directory."""
    all_metrics: dict[str, dict[str, dict]] = {}

    for bench_dir in run_dir.iterdir():
        if not bench_dir.is_dir():
            continue
        bench_name = bench_dir.name
        if bench_name in (".", ".."):
            continue

        all_metrics[bench_name] = {}
        for metrics_file in bench_dir.glob("*_metrics.json"):
            config_id = metrics_file.stem.replace("_metrics", "")
            with open(metrics_file) as f:
                all_metrics[bench_name][config_id] = json.load(f)

    return all_metrics


def load_task_results(run_dir: Path, benchmark: str, config_id: str) -> list[dict]:
    """Load per-task JSONL results."""
    results_file = run_dir / benchmark / f"{config_id}.jsonl"
    if not results_file.exists():
        return []
    with open(results_file) as f:
        return [json.loads(line) for line in f if line.strip()]


def generate_markdown_report(run_dir: Path, all_metrics: dict[str, dict[str, dict]]) -> str:
    """Generate a comprehensive markdown report."""
    lines = []
    timestamp = run_dir.name
    lines.append(f"# Benchmark Evaluation Report")
    lines.append(f"")
    lines.append(f"**Run:** {timestamp}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"")

    config_ids = set()
    for bench_metrics in all_metrics.values():
        config_ids.update(bench_metrics.keys())
    config_ids_sorted = sorted(config_ids)

    if not config_ids_sorted:
        lines.append("No results found.")
        return "\n".join(lines)

    lines.append("## Summary")
    lines.append("")

    header = "| Benchmark | " + " | ".join(config_ids_sorted) + " |"
    sep = "|" + "---|" * (len(config_ids_sorted) + 1)
    lines.append(header)
    lines.append(sep)

    for bench, bench_metrics in sorted(all_metrics.items()):
        row = f"| **{bench.upper()}** |"
        for cfg_id in config_ids_sorted:
            m = bench_metrics.get(cfg_id, {})
            if bench == "repoqa":
                val = f" {m.get('pass_rate', 0):.1%} |"
            elif bench == "sweqa":
                val = f" {m.get('avg_score', 0):.1f}/100 |"
            elif bench == "dependeval":
                val = f" {m.get('exact_match_rate', 0):.1%} |"
            else:
                val = " - |"
            row += val
        lines.append(row)

    lines.append("")

    for bench, bench_metrics in sorted(all_metrics.items()):
        lines.append(f"## {bench.upper()} Details")
        lines.append("")

        for cfg_id, metrics in sorted(bench_metrics.items()):
            lines.append(f"### Config: `{cfg_id}`")
            lines.append("")
            for key, value in metrics.items():
                if isinstance(value, float):
                    lines.append(f"- **{key}**: {value:.4f}")
                else:
                    lines.append(f"- **{key}**: {value}")
            lines.append("")

    lines.append("## Ablation Analysis")
    lines.append("")

    if "repoqa" in all_metrics:
        rm = all_metrics["repoqa"]
        full = rm.get("full_adaptive", {}).get("pass_rate", 0)
        no_lsp = rm.get("no_lsp", {}).get("pass_rate", 0)
        no_sum = rm.get("no_summaries", {}).get("pass_rate", 0)
        minimal = rm.get("minimal", {}).get("pass_rate", 0)

        if full > 0:
            lines.append("**RepoQA ablation impact (vs full_adaptive):**")
            lines.append(f"- LSP contribution: {(full - no_lsp)*100:+.1f}pp")
            lines.append(f"- Summaries contribution: {(full - no_sum)*100:+.1f}pp")
            lines.append(f"- Combined tools vs minimal: {(full - minimal)*100:+.1f}pp")
            lines.append("")

    if "sweqa" in all_metrics:
        sm = all_metrics["sweqa"]
        full = sm.get("full_adaptive", {}).get("avg_score", 0)
        no_lsp = sm.get("no_lsp", {}).get("avg_score", 0)
        no_sum = sm.get("no_summaries", {}).get("avg_score", 0)
        minimal = sm.get("minimal", {}).get("avg_score", 0)

        if full > 0:
            lines.append("**SWE-QA ablation impact (vs full_adaptive):**")
            lines.append(f"- LSP contribution: {full - no_lsp:+.1f} points")
            lines.append(f"- Summaries contribution: {full - no_sum:+.1f} points")
            lines.append(f"- Combined tools vs minimal: {full - minimal:+.1f} points")
            lines.append("")

    return "\n".join(lines)


def generate_summary_json(all_metrics: dict[str, dict[str, dict]], run_dir: Path) -> dict:
    """Generate structured summary JSON."""
    return {
        "run_id": run_dir.name,
        "generated_at": datetime.now().isoformat(),
        "benchmarks": all_metrics,
    }


@app.command()
def generate(
    run_path: Optional[str] = typer.Argument(None, help="Path to results directory"),
    latest: bool = typer.Option(False, "--latest", help="Use latest results run"),
) -> None:
    """Generate a report from benchmark results."""
    if latest or run_path is None:
        run_dir = find_latest_run()
        if run_dir is None:
            console.print("[red]No results found.[/red]")
            raise typer.Exit(1)
    else:
        run_dir = Path(run_path)

    if not run_dir.exists():
        console.print(f"[red]Results directory not found: {run_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Generating report for:[/bold] {run_dir}")
    all_metrics = load_metrics(run_dir)

    if not all_metrics:
        console.print("[yellow]No metrics files found in results directory.[/yellow]")
        raise typer.Exit(1)

    report_md = generate_markdown_report(run_dir, all_metrics)
    report_path = run_dir / "report.md"
    report_path.write_text(report_md)
    console.print(f"  [green]Markdown report:[/green] {report_path}")

    summary = generate_summary_json(all_metrics, run_dir)
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    console.print(f"  [green]Summary JSON:[/green] {summary_path}")

    _display_table(all_metrics)


def _display_table(all_metrics: dict[str, dict[str, dict]]):
    """Print a rich table to console."""
    table = Table(title="Benchmark Results")
    table.add_column("Benchmark", style="bold")

    config_ids = set()
    for bench_metrics in all_metrics.values():
        config_ids.update(bench_metrics.keys())
    config_ids_sorted = sorted(config_ids)

    for cid in config_ids_sorted:
        table.add_column(cid, justify="center")

    for bench, bench_metrics in sorted(all_metrics.items()):
        row = [bench.upper()]
        for cid in config_ids_sorted:
            m = bench_metrics.get(cid, {})
            if bench == "repoqa":
                row.append(f"{m.get('pass_rate', 0):.1%}")
            elif bench == "sweqa":
                row.append(f"{m.get('avg_score', 0):.1f}")
            elif bench == "dependeval":
                row.append(f"{m.get('exact_match_rate', 0):.1%}")
            else:
                row.append("-")
        table.add_row(*row)

    console.print(table)


if __name__ == "__main__":
    app()
