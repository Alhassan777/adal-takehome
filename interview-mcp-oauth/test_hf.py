"""
Interactive test for MCP OAuth against Hugging Face's MCP server.

Usage:
    python test_hf.py
    python test_hf.py --url https://huggingface.co/mcp
"""

import sys
import argparse
from agent import Agent


def main():
    parser = argparse.ArgumentParser(description="Test MCP OAuth with Hugging Face")
    parser.add_argument("--transport", choices=["sse", "http"],
                        default="http")
    parser.add_argument("--url", default="https://huggingface.co/mcp?login")
    args = parser.parse_args()

    print("=" * 60)
    print("🧪 Hugging Face MCP OAuth Test")
    print(f"   Transport: {args.transport}")
    print(f"   URL: {args.url}")
    print("=" * 60)

    agent = Agent()
    agent.add_mcp(args.transport, args.url)

    print(f"\n{'=' * 60}")
    print("🤖 Agent: List models on Hugging Face")
    print("-" * 60)

    answer = agent.run("List the top 5 most downloaded models on Hugging Face. Show the model name and download count for each.")

    print(f"\n💬 Agent:\n{answer}")

    assert answer and answer != "(no response)", "Agent gave no answer"

    print(f"\n{'=' * 60}")
    print("✅ Hugging Face MCP OAuth test PASSED")


if __name__ == "__main__":
    main()
