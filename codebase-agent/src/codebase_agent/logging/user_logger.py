"""User-facing logger: real-time progress feed + summary panel."""

from typing import Any, Literal

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

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
        lines = [
            f"  Question type:  {summary.question_type}",
            f"  Files analyzed: {summary.files_analyzed}",
            f"  Symbols found:  {summary.symbols_found}",
            f"  Tools called:   {summary.tools_called}",
            f"  Duration:       {summary.duration_seconds:.1f}s",
            f"  Confidence:     {summary.confidence}",
        ]
        if summary.total_tokens > 0:
            lines.append(f"  Tokens used:    {summary.total_tokens:,}")
        if summary.est_cost_usd > 0:
            lines.append(f"  Est. cost:      ${summary.est_cost_usd:.4f}")
        self.console.print(Panel("\n".join(lines), title="Analysis Summary"))

    def show_tool_suggestions_header(self, count: int) -> None:
        """Render the header for tool suggestions section."""
        if self.verbosity == "quiet":
            return
        self.console.print()
        self.console.rule("[bold cyan]Suggested Tools[/bold cyan]")
        self.console.print(
            f"\nThe agent identified [bold]{count}[/bold] reusable pattern(s) from this exploration:\n"
        )

    def show_tool_proposal(self, index: int, proposal: dict[str, Any]) -> None:
        """Render a single tool proposal with name, description, code, and rationale."""
        if self.verbosity == "quiet":
            return
        name = proposal.get("name", "unnamed")
        description = proposal.get("description", "")
        code = proposal.get("code", "")
        rationale = proposal.get("rationale", "")

        header = Text()
        header.append(f" {index}. ", style="bold")
        header.append(name, style="bold cyan")
        header.append(f"  {description}", style="dim")

        self.console.print(header)
        if code:
            self.console.print(Syntax(code, "python", theme="monokai", padding=1))
        if rationale:
            self.console.print(f"    [dim]Rationale:[/dim] {rationale}")
        self.console.print()

    def show_tool_promotion_result(self, name: str, result: dict[str, Any]) -> None:
        """Display the outcome of a tool promotion attempt."""
        if self.verbosity == "quiet":
            return
        approved = result.get("approved", False)
        feedback = result.get("feedback", "")
        if approved:
            self.console.print(f"    [green]Validated:[/green] {feedback}")
        else:
            self.console.print(f"    [yellow]Rejected:[/yellow] {feedback}")

    def show_tool_skipped(self, name: str) -> None:
        """Show that a user declined a tool suggestion."""
        if self.verbosity == "quiet":
            return
        self.console.print(f"    [dim]Skipped.[/dim]")

    def error(self, message: str) -> None:
        self.console.print(f"[red]Error: {message}[/red]")
