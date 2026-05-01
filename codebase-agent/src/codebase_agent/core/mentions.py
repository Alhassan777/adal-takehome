"""Derived lookup structures for @-mentioned files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models import MentionedFile, RepoIndex


@dataclass
class MentionResolver:
    """Cached file lookup data derived from a RepoIndex."""

    root_path: str
    file_entries: list[tuple[str, str, str]] = field(default_factory=list)
    path_index: dict[str, str] = field(default_factory=dict)
    name_index: dict[str, str] = field(default_factory=dict)
    lower_entries: list[tuple[str, str]] = field(default_factory=list)
    symbols_by_file: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_index(cls, index: RepoIndex, root_path: str | None = None) -> "MentionResolver":
        resolver = cls(root_path=root_path or index.root_path)
        resolver.refresh(index, root_path)
        return resolver

    def refresh(self, index: RepoIndex, root_path: str | None = None) -> None:
        """Rebuild all derived mention lookup data from the current index."""
        if root_path is not None:
            self.root_path = root_path
        else:
            self.root_path = index.root_path

        file_paths = sorted(f.path for f in index.files)
        self.file_entries = [
            (path, path.lower(), Path(path).name.lower())
            for path in file_paths
        ]
        self.path_index = {path: path for path in file_paths}
        self.name_index = {}
        self.lower_entries = []

        for path in file_paths:
            self.name_index.setdefault(Path(path).name, path)
            self.lower_entries.append((path, path.lower()))

        symbols_by_file: dict[str, list[str]] = {}
        for symbol in index.symbols:
            symbols_by_file.setdefault(symbol.file_path, []).append(symbol.name)
        self.symbols_by_file = symbols_by_file

    def resolve(self, mention: str) -> MentionedFile | None:
        """Resolve a mention string to a file preview and symbols."""
        if mention in self.path_index:
            return self._build_mentioned_file(self.path_index[mention])

        mention_name = Path(mention).name
        if mention_name in self.name_index:
            return self._build_mentioned_file(self.name_index[mention_name])

        m_lower = mention.lower()
        for path, path_lower in self.lower_entries:
            if m_lower in path_lower:
                return self._build_mentioned_file(path)

        return None

    def _build_mentioned_file(self, path: str) -> MentionedFile:
        abs_path = Path(self.root_path) / path
        preview = ""
        try:
            lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
            preview = "\n".join(lines[:50])
        except OSError:
            pass

        return MentionedFile(
            path=path,
            content_preview=preview,
            symbols=self.symbols_by_file.get(path, []),
        )
