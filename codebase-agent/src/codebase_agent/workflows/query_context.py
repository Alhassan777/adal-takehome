"""Prompt context helpers for parsed user queries."""

from __future__ import annotations

from ..models import ParsedQuery

MAX_MENTIONED_FILES = 5
MAX_SYMBOLS_PER_FILE = 20
MAX_PREVIEW_CHARS = 2000


def build_mentioned_files_context(parsed_query: ParsedQuery) -> str:
    """Format @mentioned files as compact, structured prompt context."""
    if not parsed_query.mentioned_files:
        return ""

    sections = ["Mentioned files supplied by the user:"]
    for mentioned in parsed_query.mentioned_files[:MAX_MENTIONED_FILES]:
        symbols = ", ".join(mentioned.symbols[:MAX_SYMBOLS_PER_FILE]) or "none"
        preview = mentioned.content_preview[:MAX_PREVIEW_CHARS].strip()
        sections.append(
            "\n".join(
                [
                    f"- Path: {mentioned.path}",
                    f"  Symbols: {symbols}",
                    "  Preview:",
                    _indent_preview(preview or "(no preview available)"),
                ]
            )
        )
    return "\n\n".join(sections)


def build_user_message(parsed_query: ParsedQuery) -> str:
    """Combine the clean question and explicit file context for LLM engines."""
    question = parsed_query.clean_query or parsed_query.raw_query
    mention_context = build_mentioned_files_context(parsed_query)
    if not mention_context:
        return question
    return f"Question: {question}\n\n{mention_context}"


def _indent_preview(preview: str) -> str:
    return "\n".join(f"    {line}" for line in preview.splitlines())
