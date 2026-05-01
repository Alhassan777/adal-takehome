"""Tests for the chat REPL: session reuse, resolver persistence, live refresh."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.core.mentions import MentionResolver
from codebase_agent.cli.completer import AtMentionCompleter, parse_query


def _sample_repo(tmp_path: Path) -> str:
    (tmp_path / "models.py").write_text(
        "class User:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "def normalize_name(name: str) -> str:\n    return name.strip().lower()\n",
        encoding="utf-8",
    )
    (tmp_path / "services.py").write_text(
        "def authenticate() -> bool:\n    return True\n",
        encoding="utf-8",
    )
    return str(tmp_path)


def test_completer_reads_resolver_live(tmp_path):
    """AtMentionCompleter reads mention_resolver.file_entries by reference,
    not a snapshot, so updates to the resolver are visible immediately."""
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    completer = AtMentionCompleter(resolver)

    original_count = len(completer.mention_resolver.file_entries)
    assert original_count >= 3

    # Simulate adding a new file and refreshing
    (tmp_path / "new_module.py").write_text("x = 1\n", encoding="utf-8")
    idx2 = build_index(repo_path)
    resolver.refresh(idx2, repo_path)

    assert len(completer.mention_resolver.file_entries) == original_count + 1


def test_resolver_refresh_updates_file_entries(tmp_path):
    """After refresh(), file_entries reflects the new index state."""
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)

    paths_before = {e[0] for e in resolver.file_entries}
    assert "models.py" in paths_before
    assert "new_module.py" not in paths_before

    (tmp_path / "new_module.py").write_text("y = 2\n", encoding="utf-8")
    idx2 = build_index(repo_path)
    resolver.refresh(idx2, repo_path)

    paths_after = {e[0] for e in resolver.file_entries}
    assert "new_module.py" in paths_after


def test_resolver_identity_preserved_across_queries(tmp_path):
    """The same MentionResolver object is used for multiple parse_query calls,
    matching the chat REPL pattern where session.mention_resolver is reused."""
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)

    parsed1 = parse_query("Explain @models.py", resolver)
    parsed2 = parse_query("Show @utils.py", resolver)

    assert len(parsed1.mentioned_files) == 1
    assert parsed1.mentioned_files[0].path == "models.py"
    assert len(parsed2.mentioned_files) == 1
    assert parsed2.mentioned_files[0].path == "utils.py"


def test_completer_sees_deleted_files_after_refresh(tmp_path):
    """After a file is deleted and index refreshed, the completer no longer lists it."""
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    completer = AtMentionCompleter(resolver)

    paths_before = {e[0] for e in completer.mention_resolver.file_entries}
    assert "services.py" in paths_before

    (tmp_path / "services.py").unlink()
    idx2 = build_index(repo_path)
    resolver.refresh(idx2, repo_path)

    paths_after = {e[0] for e in completer.mention_resolver.file_entries}
    assert "services.py" not in paths_after


def test_resolver_symbols_update_on_refresh(tmp_path):
    """symbols_by_file updates when the index is refreshed with new symbols."""
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)

    assert "User" in resolver.symbols_by_file.get("models.py", [])

    (tmp_path / "models.py").write_text(
        "class User:\n    pass\n\nclass Product:\n    pass\n",
        encoding="utf-8",
    )
    idx2 = build_index(repo_path)
    resolver.refresh(idx2, repo_path)

    symbols = resolver.symbols_by_file.get("models.py", [])
    assert "User" in symbols
    assert "Product" in symbols
