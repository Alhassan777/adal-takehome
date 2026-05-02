"""
MCP client with OAuth 2.1 authorization support.

Usage:
    agent = Agent()
    agent.add_mcp("http", "https://mcp.notion.com/mcp")
    answer = agent.run("List all documents in my Notion workspace.")
"""

import argparse
import base64
import hashlib
import json
import re
import secrets
import threading
import time
from queue import Queue, Empty
from urllib.parse import urlencode, urlparse, parse_qs

import httpx
from openai import OpenAI


# ──────────────────────────────────────────────
# PKCE (RFC 7636)
# ──────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256."""
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ──────────────────────────────────────────────
# OAuth 2.1 Discovery & Authorization
# ──────────────────────────────────────────────

def _probe_for_401(mcp_url: str, client: httpx.Client) -> httpx.Response | None:
    """Send a bare initialize to the MCP server expecting a 401."""
    try:
        return client.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-oauth-agent", "version": "1.0.0"},
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
    except httpx.HTTPError:
        return None


def _discover_oauth_metadata(mcp_url: str, client: httpx.Client) -> dict:
    """Walk the MCP → Resource Metadata → OAuth AS metadata chain."""
    resp = _probe_for_401(mcp_url, client)

    resource_meta_url = None
    if resp and resp.status_code == 401:
        www_auth = resp.headers.get("www-authenticate", "")
        m = re.search(r'resource_metadata="([^"]+)"', www_auth)
        if m:
            resource_meta_url = m.group(1)

    auth_server = None
    if resource_meta_url:
        try:
            rm = client.get(resource_meta_url).json()
            servers = rm.get("authorization_servers", [])
            if servers:
                auth_server = servers[0]
        except (httpx.HTTPError, json.JSONDecodeError):
            pass

    if not auth_server:
        parsed = urlparse(mcp_url)
        auth_server = f"{parsed.scheme}://{parsed.netloc}"

    wk_url = f"{auth_server.rstrip('/')}/.well-known/oauth-authorization-server"
    try:
        meta_resp = client.get(wk_url)
        if meta_resp.status_code == 200:
            return meta_resp.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        pass

    raise RuntimeError(
        f"Could not discover OAuth metadata for {mcp_url} "
        f"(tried {wk_url})"
    )


def _register_client(
    metadata: dict, client: httpx.Client, redirect_uri: str
) -> dict:
    """Dynamic Client Registration (RFC 7591)."""
    reg_endpoint = metadata.get("registration_endpoint")
    if not reg_endpoint:
        raise RuntimeError("No registration_endpoint in OAuth metadata")

    resp = client.post(
        reg_endpoint,
        json={
            "client_name": "MCP OAuth Agent",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Client registration failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()


def _do_oauth_flow(mcp_url: str) -> str:
    """Run the full interactive OAuth 2.1 + PKCE flow; return access_token."""
    client = httpx.Client(timeout=30, follow_redirects=True)
    redirect_uri = "http://localhost:3000/callback"

    metadata = _discover_oauth_metadata(mcp_url, client)
    reg = _register_client(metadata, client, redirect_uri)
    client_id = reg["client_id"]

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    scopes = metadata.get("scopes_supported")
    if scopes:
        params["scope"] = " ".join(scopes)

    auth_url = f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    print(f"\n🔐 Open this URL in your browser to authorize:\n\n{auth_url}\n")
    callback_url = input("📋 Paste the callback URL here: ").strip()

    qs = parse_qs(urlparse(callback_url).query)
    code = qs.get("code", [None])[0]
    if not code:
        raise RuntimeError("No authorization code in callback URL")

    returned_state = qs.get("state", [None])[0]
    if returned_state and returned_state != state:
        raise RuntimeError("OAuth state mismatch")

    token_resp = client.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    if token_resp.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed ({token_resp.status_code}): {token_resp.text}"
        )

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("No access_token in token response")
    return access_token


# ──────────────────────────────────────────────
# MCP Transports (Streamable HTTP + SSE)
# ──────────────────────────────────────────────

class _StreamableHTTP:
    """MCP Streamable-HTTP transport: every JSON-RPC message is a POST."""

    def __init__(self, url: str, access_token: str):
        self.url = url
        self._token = access_token
        self._client = httpx.Client(timeout=120)
        self._session_id: str | None = None
        self._next_id = 0

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def send(
        self, method: str, params: dict | None = None, *, notification: bool = False
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
            return self._parse_sse_body(resp.text)
        return resp.json()

    @staticmethod
    def _parse_sse_body(text: str) -> dict | None:
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return None


class _SSEListener(threading.Thread):
    """Background thread that keeps the SSE connection open and collects
    the ``endpoint`` URL and any server-pushed JSON-RPC responses."""

    def __init__(self, url: str, headers: dict[str, str]):
        super().__init__(daemon=True)
        self.url = url
        self.headers = headers
        self.endpoint_url: str | None = None
        self.ready = threading.Event()
        self._responses: dict[int, dict] = {}
        self._lock = threading.Lock()

    def run(self):
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

    def _dispatch(self, event_type: str, data: str):
        if event_type == "endpoint":
            parsed = urlparse(self.url)
            ep = data.strip()
            if ep.startswith("/"):
                self.endpoint_url = f"{parsed.scheme}://{parsed.netloc}{ep}"
            else:
                self.endpoint_url = ep
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


class _SSETransport:
    """MCP legacy SSE transport: GET for event stream, POST for messages."""

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
        self, method: str, params: dict | None = None, *, notification: bool = False
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


def _make_transport(kind: str, url: str, access_token: str):
    if kind == "http":
        return _StreamableHTTP(url, access_token)
    if kind == "sse":
        return _SSETransport(url, access_token)
    raise ValueError(f"Unknown transport: {kind!r}")


# ──────────────────────────────────────────────
# AGENT CLASS
# ──────────────────────────────────────────────

class Agent:
    """LLM agent with MCP tool support.

    Usage:
        agent = Agent()
        agent.add_mcp("http", "https://mcp.notion.com/mcp")
        answer = agent.run("List all documents in my Notion workspace.")
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.history: list[dict] = []
        self.tools: list[dict] = []
        self.sessions: list = []
        self._openai = OpenAI()
        self._tool_session_map: dict[str, object] = {}

    def add_mcp(self, transport: str, url: str):
        """Connect to an MCP server via OAuth and register its tools.

        This method:
        1. Generates the authorization URL and instructs the user to visit it
        2. User pastes the callback URL containing the auth code
        3. Lists available tools and registers them for use in run()

        Args:
            transport: "http" (Streamable HTTP) or "sse" (Server-Sent Events)
            url: MCP server URL
        """
        access_token = _do_oauth_flow(url)
        tp = _make_transport(transport, url, access_token)

        init_resp = tp.send("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcp-oauth-agent", "version": "1.0.0"},
        })
        tp.send("notifications/initialized", notification=True)

        self.sessions.append(tp)

        tools_resp = tp.send("tools/list")
        mcp_tools = []
        if tools_resp and "result" in tools_resp:
            mcp_tools = tools_resp["result"].get("tools", [])

        for t in mcp_tools:
            name = t["name"]
            self.tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {
                        "type": "object", "properties": {}
                    }),
                },
            })
            self._tool_session_map[name] = tp

        print(f"✅ Connected. Registered {len(mcp_tools)} tool(s).")

    def run(self, query: str) -> str:
        """Ask the agent a question. Returns the text response.

        This method:
        1. Sends the query to the LLM with registered MCP tools
        2. When the LLM requests a tool call, executes it via MCP
        3. Feeds the tool result back to the LLM
        4. Repeats until the LLM produces a final text response
        5. Maintains conversation history across calls

        Args:
            query: The user's question

        Returns:
            The agent's text response
        """
        self.history.append({"role": "user", "content": query})

        openai_tools = self.tools if self.tools else None

        for _ in range(25):
            kwargs: dict = {"model": self.model, "messages": self.history}
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            response = self._openai.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                content = choice.message.content or "(no response)"
                self.history.append({"role": "assistant", "content": content})
                return content

            self.history.append(choice.message.model_dump())

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tp = self._tool_session_map.get(fn_name)
                if tp:
                    result = tp.send("tools/call", {
                        "name": fn_name,
                        "arguments": fn_args,
                    })
                    if result and "result" in result:
                        content_parts = result["result"].get("content", [])
                        text_parts = [
                            p.get("text", json.dumps(p, default=str))
                            for p in content_parts
                        ]
                        tool_output = "\n".join(text_parts)
                    elif result and "error" in result:
                        tool_output = json.dumps(result["error"], default=str)
                    else:
                        tool_output = json.dumps(result, default=str)
                else:
                    tool_output = f"Error: no MCP session for tool {fn_name!r}"

                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                })

        final = "Reached maximum tool-call iterations."
        self.history.append({"role": "assistant", "content": final})
        return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP OAuth Client")
    parser.add_argument("--transport", choices=["sse", "http"], default="http")
    parser.add_argument("--url", required=True, help="MCP server URL")
    args = parser.parse_args()

    agent = Agent()
    agent.add_mcp(args.transport, args.url)

    print("\n🤖 Agent ready. Type your questions (Ctrl+C to quit).\n")
    while True:
        try:
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            continue
        answer = agent.run(query)
        print(f"\n💬 {answer}\n")
