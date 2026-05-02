"""Bridge MCP tool descriptors into the codebase-agent tool registry.

Converts MCP tool schemas to OpenAI function-calling format and provides
callable wrappers that forward invocations to the remote MCP server.
"""

from __future__ import annotations

from typing import Any

from .session import MCPSession


def mcp_tools_to_openai_schemas(session: MCPSession) -> list[dict[str, Any]]:
    """Convert the tools exposed by *session* into OpenAI tool schemas."""
    schemas: list[dict[str, Any]] = []
    for tool in session.list_tools():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {
                    "type": "object",
                    "properties": {},
                }),
            },
        })
    return schemas


def mcp_tool_registry(session: MCPSession) -> dict[str, Any]:
    """Return a ``{name: callable}`` registry compatible with
    :func:`codebase_agent.workflows.engine.build_tool_registry`."""
    registry: dict[str, Any] = {}
    for tool in session.list_tools():
        name = tool["name"]
        registry[name] = _make_caller(session, name)
    return registry


def _make_caller(session: MCPSession, tool_name: str):
    """Create a closure that calls *tool_name* on *session*."""
    def _call(**kwargs) -> Any:
        return session.call_tool(tool_name, kwargs)
    _call.__name__ = tool_name
    _call.__qualname__ = f"mcp.{tool_name}"
    return _call
