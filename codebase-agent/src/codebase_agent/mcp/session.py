"""High-level MCP session: connect, discover tools, call tools."""

from __future__ import annotations

import json
from typing import Any

from .oauth import run_oauth_flow
from .transport import make_transport


class MCPSession:
    """Authenticated connection to a single remote MCP server.

    Usage::

        session = MCPSession.connect("http", "https://mcp.notion.com/mcp")
        tools = session.list_tools()       # MCP tool descriptors
        result = session.call_tool("search", {"query": "hello"})
    """

    def __init__(self, transport):
        self._tp = transport
        self._tools: list[dict] = []

    @classmethod
    def connect(cls, transport_kind: str, url: str) -> "MCPSession":
        """Run the OAuth flow, establish the MCP session, and return a
        ready-to-use :class:`MCPSession`."""
        access_token = run_oauth_flow(url)
        tp = make_transport(transport_kind, url, access_token)

        tp.send("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "codebase-agent-mcp", "version": "1.0.0"},
        })
        tp.send("notifications/initialized", notification=True)

        session = cls(tp)
        session._tools = session._fetch_tools()
        return session

    def _fetch_tools(self) -> list[dict]:
        resp = self._tp.send("tools/list")
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        return []

    def list_tools(self) -> list[dict]:
        """Return the MCP tool descriptors discovered at connect time."""
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Invoke a tool on the remote MCP server and return its result."""
        resp = self._tp.send("tools/call", {"name": name, "arguments": arguments})
        if resp and "result" in resp:
            content_parts = resp["result"].get("content", [])
            texts = [
                p.get("text", json.dumps(p, default=str)) for p in content_parts
            ]
            return "\n".join(texts)
        if resp and "error" in resp:
            return json.dumps(resp["error"], default=str)
        return json.dumps(resp, default=str)
