"""Tests for lsp_client.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.lsp_client import PyrightLSP


class _FakeStderr:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b""


class _FakeProcess:
    def __init__(self, stderr):
        self.stderr = stderr


def test_is_available_returns_bool():
    result = PyrightLSP.is_available()
    assert isinstance(result, bool)


def test_lsp_init_without_start():
    lsp = PyrightLSP("/tmp")
    assert not lsp.is_running


def test_graceful_fallback_when_unavailable():
    lsp = PyrightLSP("/tmp")
    result = lsp.go_to_definition("/tmp/test.py", 0, 0)
    assert result is None


def test_find_references_without_running():
    lsp = PyrightLSP("/tmp")
    result = lsp.find_references("/tmp/test.py", 0, 0)
    assert result is None


def test_hover_without_running():
    lsp = PyrightLSP("/tmp")
    result = lsp.hover("/tmp/test.py", 0, 0)
    assert result is None


def test_stderr_drain_buffers_recent_lines():
    lsp = PyrightLSP("/tmp")
    lsp._process = _FakeProcess(_FakeStderr([b"warning one\n", b"warning two\n"]))

    lsp._start_stderr_drain()
    lsp._stderr_thread.join(timeout=1)

    assert lsp.last_stderr == ["warning one", "warning two"]
