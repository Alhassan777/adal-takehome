"""OAuth 2.1 authorization flow for MCP servers.

Implements the MCP-specific discovery chain:
    MCP server (401) -> Protected Resource Metadata -> OAuth AS Metadata
    -> Dynamic Client Registration -> Authorization Code + PKCE -> Token
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode, urlparse, parse_qs

import httpx


def pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` using S256."""
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def discover_oauth_metadata(mcp_url: str, client: httpx.Client) -> dict:
    """Walk MCP -> Resource Metadata -> OAuth AS metadata and return the AS
    metadata dict (authorization_endpoint, token_endpoint, etc.)."""

    resp: httpx.Response | None = None
    try:
        resp = client.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "codebase-agent-mcp", "version": "1.0.0"},
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
    except httpx.HTTPError:
        pass

    resource_meta_url: str | None = None
    if resp and resp.status_code == 401:
        www_auth = resp.headers.get("www-authenticate", "")
        m = re.search(r'resource_metadata="([^"]+)"', www_auth)
        if m:
            resource_meta_url = m.group(1)

    auth_server: str | None = None
    if resource_meta_url:
        try:
            rm = client.get(resource_meta_url).json()
            servers = rm.get("authorization_servers", [])
            if servers:
                auth_server = servers[0]
        except (httpx.HTTPError, ValueError):
            pass

    if not auth_server:
        parsed = urlparse(mcp_url)
        auth_server = f"{parsed.scheme}://{parsed.netloc}"

    wk_url = f"{auth_server.rstrip('/')}/.well-known/oauth-authorization-server"
    try:
        meta_resp = client.get(wk_url)
        if meta_resp.status_code == 200:
            return meta_resp.json()
    except (httpx.HTTPError, ValueError):
        pass

    raise RuntimeError(f"Could not discover OAuth metadata for {mcp_url}")


def register_client(
    metadata: dict, client: httpx.Client, redirect_uri: str
) -> dict:
    """Dynamic Client Registration (RFC 7591)."""
    reg_endpoint = metadata.get("registration_endpoint")
    if not reg_endpoint:
        raise RuntimeError("No registration_endpoint in OAuth metadata")

    resp = client.post(
        reg_endpoint,
        json={
            "client_name": "Codebase Agent MCP Client",
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


def run_oauth_flow(mcp_url: str) -> str:
    """Interactive OAuth 2.1 + PKCE flow. Returns the access token."""
    client = httpx.Client(timeout=30, follow_redirects=True)
    redirect_uri = "http://localhost:3000/callback"

    metadata = discover_oauth_metadata(mcp_url, client)
    reg = register_client(metadata, client, redirect_uri)
    client_id = reg["client_id"]

    verifier, challenge = pkce_pair()
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

    print(f"\nOpen this URL in your browser to authorize:\n\n{auth_url}\n")
    callback_url = input("Paste the callback URL here: ").strip()

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
