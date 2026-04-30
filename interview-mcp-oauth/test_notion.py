"""
Interactive test for MCP OAuth against Notion's real MCP server.

Usage:
    python test_notion.py
    python test_notion.py --transport sse --url https://mcp.notion.com/sse
"""

import sys
import argparse
from agent import Agent


def main():
    parser = argparse.ArgumentParser(description="Test MCP OAuth with Notion")
    parser.add_argument("--transport", choices=["sse", "http"],
                        default="http")
    parser.add_argument("--url", default="https://mcp.notion.com/mcp")
    args = parser.parse_args()

    print("=" * 60)
    print("🧪 Notion MCP OAuth Test")
    print(f"   Transport: {args.transport}")
    print(f"   URL: {args.url}")
    print("=" * 60)

    agent = Agent()
    agent.add_mcp(args.transport, args.url)

    print(f"\n{'=' * 60}")
    print("🤖 Agent: List all documents in Notion")
    print("-" * 60)

    answer = agent.run("List all documents in my Notion workspace. Show the title and URL for each.")

    print(f"\n💬 Agent:\n{answer}")

    assert answer and answer != "(no response)", "Agent gave no answer"

    print(f"\n{'=' * 60}")
    print("✅ Notion MCP OAuth test PASSED")


if __name__ == "__main__":
    main()
