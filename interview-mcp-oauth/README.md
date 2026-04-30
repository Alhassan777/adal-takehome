# MCP OAuth Client

An MCP Agent with OAuth 2.1 authorization.

---

## Files

```
interview-mcp-oauth/
├── agent.py              # Agent class: OAuth + MCP + LLM tool calling
├── test_notion.py        # Integration test against Notion MCP
├── docker-compose.yml
├── Dockerfile
├── .env                  # OPENAI_API_KEY
└── README.md
```

---

## Quick Start

```bash
docker compose run --rm interview-mcp-oauth python agent.py --transport http --url https://mcp.notion.com/mcp
```

---

## API

```python
from agent import Agent

agent = Agent()
agent.add_mcp("http", "https://mcp.notion.com/mcp")
answer = agent.run("List all documents in my Notion workspace.")
print(answer)
```

### `Agent(model="gpt-4o-mini")`

Create an agent instance with the specified LLM model.

### `agent.add_mcp(transport, url)`

Connect to an MCP server via OAuth. Parameters:
- `transport`: `"http"` or `"sse"`
- `url`: MCP server URL (e.g., `https://mcp.notion.com/mcp`)


### `agent.run(query) -> str`

Ask the agent a question. The LLM can call any registered MCP tool to answer.
Conversation history is maintained across calls.

---

## Environment

Requires `OPENAI_API_KEY` in `.env` for the LLM agent.


