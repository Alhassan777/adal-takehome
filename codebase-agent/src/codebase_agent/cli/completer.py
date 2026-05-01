"""@-mention file autocomplete and query parser for the CLI."""

import re

from prompt_toolkit.completion import Completer, Completion

from ..core.mentions import MentionResolver
from ..models import ParsedQuery


class AtMentionCompleter(Completer):
    """Autocomplete file paths after @ trigger.

    Holds a reference to MentionResolver so file_entries stay
    in sync when the watcher refreshes the index.
    """

    def __init__(self, mention_resolver: MentionResolver):
        self.mention_resolver = mention_resolver

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        at_pos = text.rfind("@")
        if at_pos == -1:
            return

        partial = text[at_pos + 1:]
        p = partial.lower()

        for path, path_lower, name_lower in self.mention_resolver.file_entries:
            if p in path_lower or p in name_lower:
                yield Completion(
                    path,
                    start_position=-len(partial),
                    display=path,
                )


def parse_query(raw: str, mention_resolver: MentionResolver) -> ParsedQuery:
    """Extract @file mentions, resolve to full paths, strip from query text."""
    mentions = re.findall(r"@([\w/.\-]+)", raw)
    mentioned_files = []

    for mention in mentions:
        resolved = mention_resolver.resolve(mention)
        if resolved:
            mentioned_files.append(resolved)

    clean = re.sub(r"@[\w/.\-]+", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean)

    return ParsedQuery(
        raw_query=raw,
        clean_query=clean,
        mentioned_files=mentioned_files,
    )
