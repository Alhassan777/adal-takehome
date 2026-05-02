# Codebase Navigation Agent

A Dockerized Python CLI and agent framework that gives an LLM structured tools to navigate, search, inspect, and understand large Python codebases -- treating the repository as an external environment rather than model context.

## Design Principles

The agent avoids two common failure modes:

1. **"LLM reads everything"** -- loading entire repos into context until tokens run out.
2. **"Purely structural tools"** -- tools that know names but not meaning (just ripgrep or AST).

Instead it uses a layered resolution strategy: coarse semantic summaries for navigation → symbol tools for verification → exact code spans for implementation details. Answers are always grounded in specific file paths and line numbers.

## Dual Execution Engines

The agent exposes two distinct execution strategies, selected via `EXECUTION_MODE` (defaults to `adaptive`):

### Adaptive Engine (default)

Uses OpenAI function calling with the **primary model** (`OPENAI_MODEL`, default `gpt-4o`) to drive tool selection in a structured loop. Before the loop starts, a single `OPENAI_SUB_MODEL` call classifies the question and injects the matching playbook's strategy, required tools, and failure chains as a second system message. The per-question tool budget comes from `playbook.max_tool_rounds` (2–8 depending on question type); when classification fails the loop falls back to `MAX_ADAPTIVE_ROUNDS = 15`. All tool calls are traced and emitted through the dev logger.

### RLM Engine

The agent writes arbitrary Python in a **REPL sandbox** and executes it. The primary model generates code; sub-tasks can be delegated to a separate **sub-model** (`OPENAI_SUB_MODEL`, default `gpt-4o-mini`) via `sub_call()` / `batch_sub_call()` (parallel). The REPL namespace exposes all 15+ pre-built tools, the full index data structures, and any previously learned tools. After answering, a `ToolReflector` reviews the session and may propose new reusable tools for approval. Up to `MAX_RLM_ITERATIONS = 10` REPL turns and `MAX_SUB_MODEL_DEPTH = 2` delegation levels.

## Model Configuration

Four independent model configs, each independently tunable:

| Config             | Env Var              | Default       | Role                                          |
| ------------------ | -------------------- | ------------- | --------------------------------------------- |
| Root agent         | `OPENAI_MODEL`       | `gpt-4o`      | Drives the Adaptive or RLM engine main loop   |
| Sub-model workers  | `OPENAI_SUB_MODEL`   | `gpt-4o-mini` | RLM `sub_call` / `batch_sub_call` delegations |
| Summary generation | `SUMMARY_LLM_MODEL`  | `gpt-4o-mini` | `--llm-summaries` file-level enrichment       |
| Summary batching   | `SUMMARY_BATCH_SIZE` | `5`           | Files per LLM batch in summary generation     |

Supported model families: OpenAI (GPT-4.1, GPT-4o, GPT-5.x, o3, o4-mini, etc.) and Anthropic (Claude Haiku, Sonnet, Opus -- 3.5 through 4.7). Pricing and token limits for all models are tracked in `config.py` for cost estimation.

## Architecture

```
User question
  -> classify_question()             # one gpt-4o-mini call -> WorkflowType + playbook
  -> AdaptiveEngine | RLMEngine      # selected by EXECUTION_MODE
       -> playbook hint in system prompt (strategy, tools, budget, failure chains)
       -> LLM-driven tool loop (playbook.max_tool_rounds / 10 REPL turns)
            -> search_summaries      # coarse semantic navigation
            -> get_file_summary      # per-file purpose and responsibilities
            -> get_definition        # LSP (type-aware) or tree-sitter fallback
            -> find_references       # semantic usages
            -> read_snippet          # exact code spans at line precision
            -> trace_module          # dependency chains
            -> impact_analysis       # change-risk surface
  -> ToolReflector (RLM only)        # proposes learned tools for reuse
  -> Answer with file paths and line numbers
```

Before the main tool-calling loop, a small `OPENAI_SUB_MODEL` call classifies the question into one of 23 workflow types. The matching playbook's strategy, required tools, failure chains, and per-workflow tool budget are injected as a second system message. The LLM can deviate from the hint if the question requires a different approach. If classification fails, the engine falls back to the generic prompt with the full 15-round budget.

**Hybrid resolution**: every tool prefers Pyright LSP (semantic, type-aware) and falls back to tree-sitter + ripgrep (syntactic) when LSP is unavailable.

## Workflow Classification

Every question is classified into one of **23 workflow types** across 6 tiers via a single `OPENAI_SUB_MODEL` call. Each type has a playbook defining the strategy, required tools, failure chains, and tool budget that get injected into the engine's prompt.

| Tier                 | Workflows                                                                            | Playbook budget |
| -------------------- | ------------------------------------------------------------------------------------ | --------------- |
| 1 -- Direct Lookup   | symbol_lookup, file_reading, file_listing, text_search                               | 2-3 rounds      |
| 2 -- Navigational    | goto_definition (3 variants), import_tracing, reverse_import_tracing                 | 3-4 rounds      |
| 3 -- Analytical      | feature_explanation, impact_analysis, test_discovery, call_graph, reverse_call_graph | 4-8 rounds      |
| 4 -- Structural      | module_overview, architecture_map, api_surface, dependency_graph                     | 4-6 rounds      |
| 5 -- Change-Oriented | safe_refactoring, dead_code, missing_tests, breaking_change                          | 4-6 rounds      |
| 6 -- Contextual      | follow_up, comparison, explicit_context                                              | 4-5 rounds      |

## Quick Start

### Interactive Session (recommended)

```bash
# Start a long-lived session with file watching
codebase-agent chat /path/to/repo

# You'll get an interactive prompt:
# ask> How does authentication work?
# ask> What calls @services.py?
# ask> /exit
```

The `chat` command builds the index once, watches for file changes, and lets you ask multiple questions without restarting.

### Single Question

```bash
# One-shot question (no interactive prompt)
codebase-agent ask /path/to/repo "How does authentication work?"
```

The `ask` command auto-initializes if no session cache exists.

### Docker

```bash
docker compose build
docker compose run agent init /workspace/repo
docker compose run agent ask /workspace/repo "How does authentication work?"
```

### Local Installation

```bash
pip install -r requirements.txt
pip install -e .
codebase-agent --help
```

## CLI Commands

| Command                      | Description                                              |
| ---------------------------- | -------------------------------------------------------- |
| `init <repo>`                | Initialize session: index + summaries + LSP warmup       |
| `chat <repo>`                | Interactive session: ask multiple questions (long-lived) |
| `ask <repo> <question>`      | Ask a single question (non-interactive, auto-inits)      |
| `index <repo>`               | Build index only (no summaries, no LSP)                  |
| `map <repo>`                 | Display a hierarchical annotated repo map                |
| `symbols <repo> <query>`     | Search for symbols by name                               |
| `definition <repo> <symbol>` | Get symbol definition with disambiguation                |
| `refs <repo> <symbol>`       | Find all references to a symbol                          |
| `imports <repo> <file>`      | Show imports for a file                                  |
| `summarize <repo>`           | Generate NL summaries for all files                      |
| `summary <repo> <file>`      | Show the summary for a specific file                     |
| `trace <repo>`               | View developer traces                                    |
| `workflows`                  | List all supported agent workflows                       |

### Flags

- `--no-lsp` (init, ask, chat): Skip Pyright LSP startup
- `--no-summaries` (init, ask, chat): Skip NL summary generation
- `--watch` (init, index): Watch for file changes and re-index incrementally
- `--with-summaries` (map): Include NL summaries in the repo map
- `--llm-summaries` (summarize): Use LLM for richer summaries
- `--sandbox local|docker` (ask, chat): RLM execution sandbox. `local` is currently supported; `docker` fails fast until an isolated executor is implemented.
- `--verbose / -v` (ask, chat): Show per-tool result previews
- `--quiet` (ask, chat): Only show the final JSON answer (suppresses progress)
- `--dev-log` (ask, chat): Enable developer logging and save trace to `.cache/traces/`
- `--last / --session` (trace): View the last trace or all session traces

## @-Mention File References

Use `@` followed by a filename in your question to reference specific files:

```bash
codebase-agent ask /path/to/repo "How does @services.py call @models.py?"
```

Mentioned files are resolved and injected as context into the agent's workflow.

## Summary System

Three-tier NL summaries act as the semantic navigation layer:

- **File summaries**: purpose, responsibilities, side effects, dependencies
- **Symbol summaries**: 1-2 sentence descriptions for key classes/functions
- **Directory summaries**: folder-level role and contents overview

Summaries are generated from deterministic static analysis (tree-sitter, import graph, docstrings, call edges) by default. Use `--llm-summaries` to enrich file-level summaries with the configured `SUMMARY_LLM_MODEL` for richer purpose and responsibility descriptions:

```bash
codebase-agent summarize /path/to/repo --llm-summaries
```

LLM summaries are batched (`SUMMARY_BATCH_SIZE` files per API call) and cached by file content hash -- only new or changed files are re-summarized. If the API key is missing or a batch fails, the system falls back to heuristic summaries automatically.

## LSP Integration

The agent spawns a background **Pyright** language server for semantic code intelligence:

- **go-to-definition**: Type-aware, resolves through the full type system
- **find-references**: Semantic usages (not just text matches)
- **hover**: Type signatures and docstrings
- **workspace symbols**: Cross-workspace symbol search

Falls back gracefully to tree-sitter + ripgrep when Pyright is unavailable.

## Symbol Disambiguation

5-phase resolution for ambiguous symbol names:

1. Gather all candidates with matching name
2. Exact resolution via context file imports (direct, aliased, module, relative)
3. LSP exact resolution (when available)
4. Ranked fallback with 9 scoring rules
5. Disambiguation threshold -- flags when top candidates are too close

## Learned Tools (RLM mode)

After each RLM session a `ToolReflector` analyzes the conversation and identifies patterns that could be reusable tools. It proposes these via the CLI for user approval. Approved tools are persisted (up to `MAX_LEARNED_TOOLS = 20`) and automatically injected into subsequent REPL namespaces as `learned_*` callables.

## Logging

### User-Facing (always on)

Real-time progress feed showing what the agent is doing, followed by a summary panel.

Three verbosity levels: `quiet`, `normal`, `verbose`.

### Developer (opt-in)

Full observability via `--dev-log` or `CODEBASE_AGENT_DEV_LOG=1`:

- Token tracking (per-tool, per-subtask, per-workflow)
- Tool call tracing (args, latency, success/failure)
- Workflow span trees (OpenTelemetry-inspired)
- Index profiling (build time, cache hits)
- Cost estimation (USD per model)

Traces stored as JSON in `.cache/traces/`.

## Key Design Decisions

- **tree-sitter** for parsing (error-tolerant, multi-language ready, incremental)
- **ripgrep** for text search (10-100x faster than Python `re`)
- **Pyright LSP** for semantic resolution (with graceful fallback)
- **Four relationship types**: import, test, name-reference, call (on-demand)
- **Coarse name_reference_map**: name-based for fast O(1) candidate discovery; LSP provides exact semantic references
- **msgpack** for index serialization (2-5x faster than JSON)
- **Per-file content hash** for incremental re-indexing
- **Summaries are coarse navigation, not final answers**: the agent always verifies with symbol tools

## Dependencies

**Python packages:**

- pydantic, typer, rich, networkx
- tree-sitter, tree-sitter-python
- msgpack, watchfiles, prompt_toolkit

**System (installed in Docker):**

- ripgrep, build-essential, nodejs + npm
- pyright (via `npm install -g`)

## Running Tests

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

## Limitations

- LSP requires Pyright to be installed (handled by Docker)
- Name reference map is coarse (name-based, not semantic)
- Call graph is on-demand and heuristic-based without LSP
- LLM summaries require an API key and are opt-in
- Currently supports Python files only (multi-language grammar support planned)
- RLM Docker sandbox not yet implemented (fails fast with a clear error)
