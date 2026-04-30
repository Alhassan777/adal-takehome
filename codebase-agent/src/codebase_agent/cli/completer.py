"""@-mention file autocomplete and query parser for the interactive CLI."""

import re
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion

from ..models import MentionedFile, ParsedQuery, RepoIndex


class AtMentionCompleter(Completer):
    """Autocomplete file paths after @ trigger."""

    def __init__(self, index: RepoIndex):
        self.file_paths = sorted(f.path for f in index.files)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        at_pos = text.rfind("@")
        if at_pos == -1:
            return

        partial = text[at_pos + 1:]
        p = partial.lower()

        for path in self.file_paths:
            if p in path.lower() or p in Path(path).name.lower():
                yield Completion(
                    path,
                    start_position=-len(partial),
                    display=path,
                    display_meta=self._get_role(path),
                )

    def _get_role(self, path: str) -> str:
        name = Path(path).name.lower()
        parts = Path(path).parts
        if "test" in name or "tests" in parts:
            return "test"
        if "model" in name:
            return "model"
        if "service" in name:
            return "service"
        if "util" in name or "helper" in name:
            return "utility"
        return ""


def interactive_prompt(index: RepoIndex) -> str:
    """Launch an interactive prompt with @-mention autocomplete."""
    completer = AtMentionCompleter(index)
    session: PromptSession = PromptSession(completer=completer)
    return session.prompt("ask> ")


def parse_query(raw: str, index: RepoIndex, root_path: str) -> ParsedQuery:
    """Extract @file mentions, resolve to full paths, strip from query text."""
    mentions = re.findall(r"@([\w/.\-]+)", raw)
    mentioned_files: list[MentionedFile] = []

    for mention in mentions:
        resolved = _resolve_mention(mention, index, root_path)
        if resolved:
            mentioned_files.append(resolved)

    clean = re.sub(r"@[\w/.\-]+", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean)

    return ParsedQuery(
        raw_query=raw,
        clean_query=clean,
        mentioned_files=mentioned_files,
    )


def _resolve_mention(mention: str, index: RepoIndex, root_path: str) -> MentionedFile | None:
    for f in index.files:
        if f.path == mention:
            return _build_mentioned_file(f.path, index, root_path)
    mention_name = Path(mention).name
    for f in index.files:
        if Path(f.path).name == mention_name:
            return _build_mentioned_file(f.path, index, root_path)
    m_lower = mention.lower()
    for f in index.files:
        if m_lower in f.path.lower():
            return _build_mentioned_file(f.path, index, root_path)
    return None


def _build_mentioned_file(path: str, index: RepoIndex, root_path: str) -> MentionedFile:
    abs_path = Path(root_path) / path
    preview = ""
    try:
        lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        preview = "\n".join(lines[:50])
    except OSError:
        pass
    file_symbols = [s.name for s in index.symbols if s.file_path == path]
    return MentionedFile(path=path, content_preview=preview, symbols=file_symbols)
