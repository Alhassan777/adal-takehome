"""Tests for cli completer (parse_query @-mention resolution)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.core.mentions import MentionResolver
from codebase_agent.cli.completer import parse_query


def _sample_repo(tmp_path: Path) -> str:
    (tmp_path / "models.py").write_text(
        "class User:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "def normalize_name(name: str) -> str:\n"
        "    return name.strip().lower()\n",
        encoding="utf-8",
    )
    (tmp_path / "services.py").write_text(
        "def authenticate() -> bool:\n"
        "    return True\n",
        encoding="utf-8",
    )
    return str(tmp_path)


def test_parse_query_extracts_mentions(tmp_path):
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    parsed = parse_query("How does @models.py work?", resolver)
    assert parsed.clean_query == "How does work?"
    assert len(parsed.mentioned_files) == 1
    assert parsed.mentioned_files[0].path == "models.py"


def test_parse_query_handles_no_mentions(tmp_path):
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    parsed = parse_query("How does auth work?", resolver)
    assert parsed.clean_query == "How does auth work?"
    assert len(parsed.mentioned_files) == 0


def test_parse_query_resolves_partial_name(tmp_path):
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    parsed = parse_query("Explain @utils", resolver)
    assert len(parsed.mentioned_files) == 1
    assert "utils" in parsed.mentioned_files[0].path


def test_mentioned_file_has_symbols(tmp_path):
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    parsed = parse_query("Show @models.py", resolver)
    assert len(parsed.mentioned_files) == 1
    assert len(parsed.mentioned_files[0].symbols) > 0


def test_parse_query_multiple_mentions(tmp_path):
    repo_path = _sample_repo(tmp_path)
    idx = build_index(repo_path)
    resolver = MentionResolver.from_index(idx, repo_path)
    parsed = parse_query("How does @services.py call @models.py?", resolver)
    assert parsed.clean_query == "How does call ?"
    assert len(parsed.mentioned_files) == 2
