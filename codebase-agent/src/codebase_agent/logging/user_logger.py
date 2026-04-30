"""User-facing logger: real-time progress feed + summary panel."""

from typing import Literal

from rich.console import Console
from rich.panel import Panel

from ..models import UserSummary


class UserLogger:
    """Shows real-time progress and end-of-workflow summary to the user."""

    def __init__(
        self,
        verbosity: Literal["quiet", "normal", "verbose"] = "normal",
        console: Console | None = None,
    ) -> None:
        self.verbosity = verbosity
        self.console = console or Console()

    def start_workflow(self, question: str, workflow_type: str) -> None:
        if self.verbosity == "quiet":
            return
        self.console.print(f'\nAnalyzing question: "{question}"')
        self.console.print(f"  Classified as: [bold]{workflow_type}[/bold]")

    def start_subtask(self, index: int, total: int, description: str) -> None:
        if self.verbosity == "quiet":
            return
        self.console.print(f"\n  [{index}/{total}] {description}...")

    def subtask_result(self, brief: str) -> None:
        if self.verbosity == "quiet":
            return
        self.console.print(f"        {brief}")

    def tool_preview(self, tool_name: str, result_preview: str) -> None:
        if self.verbosity != "verbose":
            return
        self.console.print(f"        [dim]{tool_name}: {result_preview[:100]}[/dim]")

    def end_workflow(self, summary: UserSummary) -> None:
        if self.verbosity == "quiet":
            return
        panel_content = (
            f"  Question type:  {summary.question_type}\n"
            f"  Files analyzed: {summary.files_analyzed}\n"
            f"  Symbols found:  {summary.symbols_found}\n"
            f"  Tools called:   {summary.tools_called}\n"
            f"  Duration:       {summary.duration_seconds:.1f}s\n"
            f"  Confidence:     {summary.confidence}"
        )
        self.console.print(Panel(panel_content, title="Analysis Summary"))

    def error(self, message: str) -> None:
        self.console.print(f"[red]Error: {message}[/red]")
