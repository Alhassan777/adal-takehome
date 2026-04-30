"""Tests for user-facing logging."""

import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console

from codebase_agent.logging.user_logger import UserLogger
from codebase_agent.models import UserSummary


def _make_logger(verbosity="normal") -> tuple[UserLogger, StringIO]:
    output = StringIO()
    console = Console(file=output, width=120)
    logger = UserLogger(verbosity=verbosity, console=console)
    return logger, output


def test_normal_verbosity_shows_progress():
    logger, output = _make_logger("normal")
    logger.start_workflow("How does auth work?", "feature_explanation")
    logger.start_subtask(1, 3, "Searching symbols")
    logger.subtask_result("Found 5 symbols")
    text = output.getvalue()
    assert "auth" in text
    assert "Searching symbols" in text
    assert "Found 5 symbols" in text


def test_quiet_verbosity_hides_progress():
    logger, output = _make_logger("quiet")
    logger.start_workflow("test", "test_type")
    logger.start_subtask(1, 2, "doing stuff")
    logger.subtask_result("done")
    text = output.getvalue()
    assert text == ""


def test_verbose_shows_tool_preview():
    logger, output = _make_logger("verbose")
    logger.tool_preview("search_text", "found 10 matches in models.py")
    text = output.getvalue()
    assert "search_text" in text


def test_normal_hides_tool_preview():
    logger, output = _make_logger("normal")
    logger.tool_preview("search_text", "found 10 matches")
    text = output.getvalue()
    assert text == ""


def test_end_workflow_shows_summary_panel():
    logger, output = _make_logger("normal")
    summary = UserSummary(
        question_type="feature_explanation",
        files_analyzed=6,
        symbols_found=12,
        tools_called=8,
        duration_seconds=1.2,
        confidence="high",
    )
    logger.end_workflow(summary)
    text = output.getvalue()
    assert "6" in text
    assert "12" in text
    assert "high" in text
