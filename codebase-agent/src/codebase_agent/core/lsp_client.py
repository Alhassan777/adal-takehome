"""Pyright LSP client: spawn server, communicate via JSON-RPC over stdin/stdout."""

import json
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any


class PyrightLSP:
    """Manages a background Pyright language server for semantic code intelligence."""

    def __init__(self, root_path: str):
        self._root_path = str(Path(root_path).resolve())
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._initialized = False
        self._stderr_lines: deque[str] = deque(maxlen=50)
        self._stderr_thread: threading.Thread | None = None

    @staticmethod
    def is_available() -> bool:
        return shutil.which("pyright-langserver") is not None

    def start(self) -> bool:
        if not self.is_available():
            return False
        try:
            self._process = subprocess.Popen(
                ["pyright-langserver", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._start_stderr_drain()
            self._initialize()
            self._initialized = True
            return True
        except (OSError, FileNotFoundError):
            self._process = None
            return False

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._send_request("shutdown", {})
            self._send_notification("exit", {})
            self._process.wait(timeout=5)
        except Exception:
            if self._process:
                self._process.kill()
        finally:
            self._process = None
            self._initialized = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def last_stderr(self) -> list[str]:
        """Recent stderr lines captured from the language server."""
        return list(self._stderr_lines)

    def go_to_definition(self, file_path: str, line: int, character: int) -> list[dict] | None:
        """textDocument/definition -> list of locations."""
        if not self.is_running:
            return None
        uri = self._path_to_uri(file_path)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }
        result = self._send_request("textDocument/definition", params)
        if result is None:
            return None
        if isinstance(result, dict):
            return [self._parse_location(result)]
        if isinstance(result, list):
            return [self._parse_location(loc) for loc in result]
        return None

    def find_references(self, file_path: str, line: int, character: int) -> list[dict] | None:
        """textDocument/references -> list of locations."""
        if not self.is_running:
            return None
        uri = self._path_to_uri(file_path)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        }
        result = self._send_request("textDocument/references", params)
        if result is None:
            return None
        if isinstance(result, list):
            return [self._parse_location(loc) for loc in result]
        return None

    def hover(self, file_path: str, line: int, character: int) -> str | None:
        """textDocument/hover -> hover text."""
        if not self.is_running:
            return None
        uri = self._path_to_uri(file_path)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }
        result = self._send_request("textDocument/hover", params)
        if result and isinstance(result, dict):
            contents = result.get("contents", "")
            if isinstance(contents, dict):
                return contents.get("value", "")
            if isinstance(contents, str):
                return contents
        return None

    def workspace_symbols(self, query: str) -> list[dict] | None:
        """workspace/symbol -> list of symbol information."""
        if not self.is_running:
            return None
        result = self._send_request("workspace/symbol", {"query": query})
        if result is None:
            return None
        if isinstance(result, list):
            return [
                {
                    "name": s.get("name", ""),
                    "kind": s.get("kind", 0),
                    "file": self._uri_to_path(s.get("location", {}).get("uri", "")),
                    "line": s.get("location", {}).get("range", {}).get("start", {}).get("line", 0),
                }
                for s in result
            ]
        return None

    def _initialize(self) -> None:
        params = {
            "processId": None,
            "rootUri": self._path_to_uri(self._root_path),
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                },
                "workspace": {
                    "symbol": {"dynamicRegistration": False},
                },
            },
        }
        self._send_request("initialize", params)
        self._send_notification("initialized", {})

    def _start_stderr_drain(self) -> None:
        if self._process is None or self._process.stderr is None:
            return

        def _drain() -> None:
            stderr = self._process.stderr
            while True:
                line = stderr.readline()
                if not line:
                    break
                self._stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())

        self._stderr_thread = threading.Thread(target=_drain, daemon=True)
        self._stderr_thread.start()

    def _send_request(self, method: str, params: dict) -> Any:
        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        self._write_message(message)
        return self._read_response(req_id)

    def _send_notification(self, method: str, params: dict) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message(message)

    def _write_message(self, message: dict) -> None:
        if self._process is None or self._process.stdin is None:
            return
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._process.stdin.write(header + body)
        self._process.stdin.flush()

    def _read_response(self, expected_id: int) -> Any:
        if self._process is None or self._process.stdout is None:
            return None
        while True:
            header_line = b""
            while True:
                byte = self._process.stdout.read(1)
                if not byte:
                    return None
                header_line += byte
                if header_line.endswith(b"\r\n\r\n"):
                    break

            content_length = 0
            for line in header_line.decode("ascii").split("\r\n"):
                if line.startswith("Content-Length:"):
                    content_length = int(line.split(":")[1].strip())

            if content_length == 0:
                return None

            body = self._process.stdout.read(content_length)
            if not body:
                return None

            try:
                msg = json.loads(body)
            except json.JSONDecodeError:
                continue

            if msg.get("id") == expected_id:
                return msg.get("result")

    def _path_to_uri(self, path: str) -> str:
        return "file://" + str(Path(path).resolve())

    def _uri_to_path(self, uri: str) -> str:
        if uri.startswith("file://"):
            return uri[7:]
        return uri

    def _parse_location(self, loc: dict) -> dict:
        uri = loc.get("uri", "")
        range_info = loc.get("range", {})
        start = range_info.get("start", {})
        return {
            "file": self._uri_to_path(uri),
            "line": start.get("line", 0),
            "character": start.get("character", 0),
        }
