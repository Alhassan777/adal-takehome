"""MCP JSON-RPC transports: Streamable HTTP and legacy SSE."""

from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlparse

import httpx


class StreamableHTTPTransport:
    """Every JSON-RPC message is a single POST to the MCP endpoint."""

    def __init__(self, url: str, access_token: str):
        self.url = url
        self._token = access_token
        self._client = httpx.Client(timeout=120)
        self._session_id: str | None = None
        self._next_id = 0

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def send(
        self,
        method: str,
        params: dict | None = None,
        *,
        notification: bool = False,
    ) -> dict | None:
        self._next_id += 1
        body: dict = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = self._next_id
        if params is not None:
            body["params"] = params

        resp = self._client.post(self.url, json=body, headers=self._headers())
        resp.raise_for_status()

        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid

        if notification or resp.status_code == 202 or not resp.text.strip():
            return None

        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return _parse_sse_body(resp.text)
        return resp.json()


class _SSEListener(threading.Thread):
    """Background thread that holds the SSE stream open and collects the
    ``endpoint`` URL and any server-pushed JSON-RPC responses."""

    def __init__(self, url: str, headers: dict[str, str]):
        super().__init__(daemon=True)
        self.url = url
        self.headers = headers
        self.endpoint_url: str | None = None
        self.ready = threading.Event()
        self._responses: dict[int, dict] = {}
        self._lock = threading.Lock()

    def run(self) -> None:
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", self.url, headers=self.headers) as resp:
                event_type: str | None = None
                data_buf: list[str] = []
                for raw_line in resp.iter_lines():
                    line = raw_line.strip()
                    if not line:
                        if event_type and data_buf:
                            self._dispatch(event_type, "\n".join(data_buf))
                        event_type = None
                        data_buf = []
                        continue
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data_buf.append(line[6:])

    def _dispatch(self, event_type: str, data: str) -> None:
        if event_type == "endpoint":
            parsed = urlparse(self.url)
            ep = data.strip()
            self.endpoint_url = (
                f"{parsed.scheme}://{parsed.netloc}{ep}"
                if ep.startswith("/")
                else ep
            )
            self.ready.set()
        elif event_type == "message":
            try:
                msg = json.loads(data)
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._lock:
                        self._responses[msg_id] = msg
            except json.JSONDecodeError:
                pass

    def pop_response(self, msg_id: int, timeout: float = 30.0) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if msg_id in self._responses:
                    return self._responses.pop(msg_id)
            time.sleep(0.1)
        return None


class SSETransport:
    """Legacy MCP SSE transport: GET for event stream, POST for messages."""

    def __init__(self, url: str, access_token: str):
        self.url = url
        self._token = access_token
        self._post_client = httpx.Client(timeout=120)
        self._next_id = 0

        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._listener = _SSEListener(url, headers)
        self._listener.start()
        if not self._listener.ready.wait(timeout=30):
            raise RuntimeError("SSE endpoint event not received within 30 s")

    def _post_headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def send(
        self,
        method: str,
        params: dict | None = None,
        *,
        notification: bool = False,
    ) -> dict | None:
        self._next_id += 1
        body: dict = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = self._next_id
        if params is not None:
            body["params"] = params

        ep = self._listener.endpoint_url
        if not ep:
            raise RuntimeError("No SSE endpoint URL available")

        resp = self._post_client.post(ep, json=body, headers=self._post_headers())
        resp.raise_for_status()

        if notification:
            return None

        if resp.status_code == 200 and resp.text.strip():
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct:
                return resp.json()

        return self._listener.pop_response(body["id"])


def make_transport(kind: str, url: str, access_token: str):
    """Factory: create the appropriate transport by name."""
    if kind == "http":
        return StreamableHTTPTransport(url, access_token)
    if kind == "sse":
        return SSETransport(url, access_token)
    raise ValueError(f"Unknown MCP transport: {kind!r}")


def _parse_sse_body(text: str) -> dict | None:
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None
