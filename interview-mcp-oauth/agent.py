"""
MCP client with OAuth 2.1 authorization support.

Usage:
    agent = Agent()
    agent.add_mcp("http", "https://mcp.notion.com/mcp")
    answer = agent.run("List all documents in my Notion workspace.")
"""

import argparse
import json


# ──────────────────────────────────────────────
# AGENT CLASS — IMPLEMENT THIS
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
        self.history = []
        self.tools = []
        self.sessions = []

    def add_mcp(self, transport: str, url: str):
        """Connect to an MCP server via OAuth and register its tools.

        This method must:
        1. Generate the authorization URL and instruct the user to visit it
        2. User pastes the callback URL containing the auth code
        3. List available tools and register them for use in run()

        Args:
            transport: "http" (Streamable HTTP) or "sse" (Server-Sent Events)
            url: MCP server URL
        """
        raise NotImplementedError("Implement add_mcp")

    def run(self, query: str) -> str:
        """Ask the agent a question. Returns the text response.

        This method must:
        1. Send the query to the LLM with registered MCP tools
        2. When the LLM requests a tool call, execute it via MCP
        3. Feed the tool result back to the LLM
        4. Repeat until the LLM produces a final text response
        5. Maintain conversation history across calls

        Args:
            query: The user's question

        Returns:
            The agent's text response
        """
        raise NotImplementedError("Implement run")


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
