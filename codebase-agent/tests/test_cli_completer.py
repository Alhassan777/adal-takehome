"""Tests for cli_completer.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.cli.completer import AtMentionCompleter, parse_query
from codebase_agent.config import INDEX_DIR
import shutil

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


def _cleanup():
    shutil.rmtree(str(Path(SAMPLE_REPO) / INDEX_DIR), ignore_errors=True)


def test_completer_suggests_files():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    completer = AtMentionCompleter(idx)
    assert len(completer.file_paths) >= 3
    _cleanup()


def test_parse_query_extracts_mentions():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    parsed = parse_query("How does @models.py work?", idx, SAMPLE_REPO)
    assert parsed.clean_query == "How does work?"
    assert len(parsed.mentioned_files) == 1
    assert parsed.mentioned_files[0].path == "models.py"
    _cleanup()


def test_parse_query_handles_no_mentions():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    parsed = parse_query("How does auth work?", idx, SAMPLE_REPO)
    assert parsed.clean_query == "How does auth work?"
    assert len(parsed.mentioned_files) == 0
    _cleanup()


def test_parse_query_resolves_partial_name():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    parsed = parse_query("Explain @utils", idx, SAMPLE_REPO)
    assert len(parsed.mentioned_files) == 1
    assert "utils" in parsed.mentioned_files[0].path
    _cleanup()


def test_mentioned_file_has_symbols():
    _cleanup()
    idx = build_index(SAMPLE_REPO)
    parsed = parse_query("Show @models.py", idx, SAMPLE_REPO)
    assert len(parsed.mentioned_files) == 1
    assert len(parsed.mentioned_files[0].symbols) > 0
    _cleanup()
