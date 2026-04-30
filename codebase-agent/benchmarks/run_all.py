"""CLI entry point for running benchmark evaluations.

Usage:
    python -m benchmarks.run_all --benchmark repoqa --config full_adaptive
    python -m benchmarks.run_all --benchmark sweqa --all-configs
    python -m benchmarks.run_all --all
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.table import Table

from .configs import ALL_CONFIGS, AblationConfig, ConfigID, get_config

app = typer.Typer(
    name="benchmarks",
    help="Run benchmark evaluations for the codebase navigation agent.",
    no_args_is_help=True,
)
console = Console()

RESULTS_DIR = Path(__file__).parent / "results"

BENCHMARKS = ["repoqa", "sweqa", "dependeval"]


def _get_results_dir(timestamp: str | None = None) -> Path:
    """Get or create the results directory for this run."""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = RESULTS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _save_results(results: list[dict], benchmark: str, config_id: str, run_dir: Path) -> Path:
    """Save per-task results as JSONL."""
    bench_dir = run_dir / benchmark
    bench_dir.mkdir(parents=True, exist_ok=True)
    output_path = bench_dir / f"{config_id}.jsonl"

    with open(output_path, "w") as f:
        for result in results:
            f.write(json.dumps(result, default=str) + "\n")

    return output_path


def _run_repoqa(config: AblationConfig, run_dir: Path, max_tasks: int | None = None):
    """Execute RepoQA benchmark for a single config."""
    from .repoqa_eval import run_repoqa_evaluation, compute_metrics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"RepoQA [{config.name}]", total=max_tasks or 100
        )

        def on_progress(current, total, result):
            progress.update(task_id, completed=current, total=total)

        results = run_repoqa_evaluation(
            config, max_tasks=max_tasks, progress_callback=on_progress
        )

    metrics = compute_metrics(results)
    result_dicts = [r.to_dict() for r in results]
    output_path = _save_results(result_dicts, "repoqa", config.name, run_dir)

    metrics_path = run_dir / "repoqa" / f"{config.name}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    console.print(f"  [green]Pass rate: {metrics['pass_rate']:.1%}[/green] "
                  f"({metrics['passed']}/{metrics['total']})")
    console.print(f"  Results: {output_path}")
    return metrics


def _run_sweqa(config: AblationConfig, run_dir: Path, max_tasks: int | None = None, repos: list[str] | None = None):
    """Execute SWE-QA benchmark for a single config."""
    from .sweqa_eval import run_sweqa_evaluation, compute_metrics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"SWE-QA [{config.name}]", total=max_tasks or 144
        )

        def on_progress(current, total, result):
            progress.update(task_id, completed=current, total=total)

        results = run_sweqa_evaluation(
            config, max_tasks=max_tasks, repos=repos, progress_callback=on_progress
        )

    metrics = compute_metrics(results)
    result_dicts = [r.to_dict() for r in results]
    output_path = _save_results(result_dicts, "sweqa", config.name, run_dir)

    metrics_path = run_dir / "sweqa" / f"{config.name}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    console.print(f"  [green]Avg score: {metrics['avg_score']:.1f}/100[/green] "
                  f"({metrics['total']} questions)")
    console.print(f"  Results: {output_path}")
    return metrics


def _run_dependeval(config: AblationConfig, run_dir: Path, max_tasks: int | None = None):
    """Execute DependEval Task 1 benchmark for a single config."""
    from .dependeval_eval import run_dependeval_evaluation, compute_metrics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"DependEval [{config.name}]", total=max_tasks or 100
        )

        def on_progress(current, total, result):
            progress.update(task_id, completed=current, total=total)

        results = run_dependeval_evaluation(
            config, max_tasks=max_tasks, progress_callback=on_progress
        )

    metrics = compute_metrics(results)
    result_dicts = [r.to_dict() for r in results]
    output_path = _save_results(result_dicts, "dependeval", config.name, run_dir)

    metrics_path = run_dir / "dependeval" / f"{config.name}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    console.print(f"  [green]EMR: {metrics['exact_match_rate']:.1%}[/green] "
                  f"({metrics['matched']}/{metrics['total']})")
    console.print(f"  Results: {output_path}")
    return metrics


@app.command()
def run(
    benchmark: Optional[str] = typer.Option(None, "--benchmark", "-b", help="Benchmark to run: repoqa, sweqa, dependeval"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Config ID to use"),
    all_configs: bool = typer.Option(False, "--all-configs", help="Run all ablation configs"),
    all_benchmarks: bool = typer.Option(False, "--all", help="Run all benchmarks with all configs"),
    max_tasks: Optional[int] = typer.Option(None, "--max-tasks", "-n", help="Limit number of tasks per benchmark"),
    repos: Optional[str] = typer.Option(None, "--repos", help="Comma-separated repo names (SWE-QA only)"),
) -> None:
    """Run benchmark evaluations."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    run_dir = _get_results_dir()
    console.print(f"\n[bold]Benchmark Run[/bold]: {run_dir.name}\n")

    if all_benchmarks:
        benchmarks_to_run = BENCHMARKS
        configs_to_run = ALL_CONFIGS
    else:
        if benchmark is None:
            console.print("[red]Specify --benchmark or --all[/red]")
            raise typer.Exit(1)
        if benchmark not in BENCHMARKS:
            console.print(f"[red]Unknown benchmark: {benchmark}. Choose from: {BENCHMARKS}[/red]")
            raise typer.Exit(1)
        benchmarks_to_run = [benchmark]

        if all_configs:
            configs_to_run = ALL_CONFIGS
        elif config:
            configs_to_run = [get_config(config)]
        else:
            configs_to_run = [get_config(ConfigID.FULL_ADAPTIVE)]

    repo_list = repos.split(",") if repos else None
    all_metrics: dict[str, dict[str, dict]] = {}

    for bench in benchmarks_to_run:
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold]Benchmark: {bench.upper()}[/bold]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")
        all_metrics[bench] = {}

        for cfg in configs_to_run:
            console.print(f"\n[bold]Config: {cfg.name}[/bold] ({cfg.description})")

            if bench == "repoqa":
                metrics = _run_repoqa(cfg, run_dir, max_tasks)
            elif bench == "sweqa":
                metrics = _run_sweqa(cfg, run_dir, max_tasks, repo_list)
            elif bench == "dependeval":
                metrics = _run_dependeval(cfg, run_dir, max_tasks)
            else:
                continue

            all_metrics[bench][cfg.name] = metrics

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(all_metrics, f, indent=2)

    console.print(f"\n[bold green]All done![/bold green] Summary: {summary_path}")
    _print_summary_table(all_metrics)


def _print_summary_table(all_metrics: dict[str, dict[str, dict]]):
    """Print a summary comparison table."""
    table = Table(title="\nBenchmark Results Summary")
    table.add_column("Benchmark", style="bold")

    config_names = set()
    for bench_metrics in all_metrics.values():
        config_names.update(bench_metrics.keys())
    config_names_sorted = sorted(config_names)

    for name in config_names_sorted:
        table.add_column(name, justify="center")

    for bench, bench_metrics in all_metrics.items():
        row = [bench.upper()]
        for cfg_name in config_names_sorted:
            m = bench_metrics.get(cfg_name, {})
            if bench == "repoqa":
                val = f"{m.get('pass_rate', 0):.1%}"
            elif bench == "sweqa":
                val = f"{m.get('avg_score', 0):.1f}"
            elif bench == "dependeval":
                val = f"{m.get('exact_match_rate', 0):.1%}"
            else:
                val = "-"
            row.append(val)
        table.add_row(*row)

    console.print(table)


if __name__ == "__main__":
    app()
