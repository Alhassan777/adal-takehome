# Interview Challenge: Code Navigation Agent

**Time**: 15–30 minutes
**Goal**: Build tools that let an LLM agent navigate and understand a Python codebase.

---

## What You're Given

```
/workspace/
├── agent.py              # Working LLM agent loop (OpenAI SDK)
├── sample_project/       # Python project to analyze
│   ├── models.py         # User, Task, Project dataclasses
│   ├── services.py       # Uses models + utils
│   └── utils.py          # Helper functions
├── test.py                   # End-to-end test suite
└── README.md             # This file
```

### `agent.py`

A working chat agent that talks to GPT via the OpenAI SDK and supports tool calling. It has two extension points:

- **`TOOLS`** — a list of [OpenAI function-calling tool definitions](https://platform.openai.com/docs/guides/function-calling)
- **`HANDLERS`** — a dict mapping tool names to Python functions

### `sample_project/`

A small Python project with cross-file imports. `services.py` imports from `models.py` and `utils.py`.

---

## Your Task

Make the agent capable of navigating the codebase — finding where symbols are defined, reading files, and searching for code. The test suite will verify your implementation.

---

## Running the Agent

```bash
docker compose run --rm interview-lsp python agent.py
```

## Test Suite

Run the tests inside Docker:

```bash
docker compose run --rm interview-lsp python test.py
```

The test sends natural language queries through the full agent loop and checks that the agent's responses contain the correct information.

### Test 1 — Find `User` (with position hint)

The agent is told that `User` is at line 2, character 21 in `services.py`. It should find the definition and return the complete class including the `display_name` method.

### Test 2 — Find `Task` (with position hint)

Same as above for `Task` at line 2, character 28 in `services.py`. Should return the complete class including the `completed` field.

### Test 3 — Find `format_date` (no position hint)

The agent is only told the file. It must read the file, locate where `format_date` is used, determine the position, and jump to its definition in `utils.py`. Should include the `strftime` implementation.

### Test 4 — Find `Project` (no position hint)

Same approach — read the file, find the symbol, navigate to the definition. Should include the `pending_tasks` method.

### Test 5 — Find `truncate` (no file hint)

The agent is only told the project directory. It must search across files to find where `truncate` is defined, then show the complete implementation including the `length` parameter.

### Test 6 — Find `pending_tasks` (no file hint)

Same approach — search the project for `pending_tasks`, find its definition in `models.py`, and show the implementation referencing `completed`.

---

## Bonus: Custom Tool Calling

Once all 6 tests pass, refactor the agent to use your own tool calling protocol **without using OpenAI's `tools` parameter**. The LLM should describe tool calls in its text response (e.g., using XML tags or JSON blocks), and your code should parse and execute them. All 6 tests must still pass after this change.

---

## Evaluation Criteria

| Criterion | What we're looking for |
|-----------|----------------------|
| **All tests pass** | Agent correctly navigates the codebase end-to-end |
| **Tool design** | Clean schemas, clear descriptions, proper error handling |
| **Environment setup** | Appropriate tools installed and configured |
| **Code quality** | Readable, well-structured implementation |
| **Communication** | Explains approach and tradeoffs as they work |
