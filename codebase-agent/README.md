# Codebase Navigation Agent

A Dockerized Python tool server and CLI that gives an LLM agent structured tools to navigate, search, inspect, and understand large Python codebases -- treating the repository as an external environment (RLM-inspired), not model context.

## Design Principle: RLM-Inspired Navigation

Recursive Language Models treat the codebase as an **external environment** rather than loading everything into model context. The agent:

1. Starts with **summaries** (coarse navigation layer)
2. Narrows to **specific files** using symbol search and references
3. Reads only the **exact code spans** needed to answer

This avoids the "LLM reads everything" problem while also avoiding the opposite: purely structural tools that know names but not meaning.

## Architecture

```
User question
  -> search_summaries(query)          # find likely files/modules
  -> get_file_summary(path)           # understand purpose before reading
  -> get_definition / find_references # verify with precise tools
  -> read_snippet                     # open exact code spans
  -> Answer with grounded file paths and line numbers
```

**Hybrid resolution**: each tool prefers LSP (semantic, type-aware) and falls back to tree-sitter + ripgrep (syntactic) when LSP is unavailable.

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

| Command | Description |
|---------|-------------|
| `init <repo>` | Initialize session: index + summaries + LSP warmup |
| `chat <repo>` | Interactive session: ask multiple questions (long-lived) |
| `ask <repo> <question>` | Ask a single question (non-interactive, auto-inits) |
| `index <repo>` | Build index only (no summaries, no LSP) |
| `map <repo>` | Display a hierarchical annotated repo map |
| `symbols <repo> <query>` | Search for symbols by name |
| `definition <repo> <symbol>` | Get symbol definition with disambiguation |
| `refs <repo> <symbol>` | Find all references to a symbol |
| `imports <repo> <file>` | Show imports for a file |
| `summarize <repo>` | Generate NL summaries for all files |
| `summary <repo> <file>` | Show the summary for a specific file |
| `trace <repo>` | View developer traces |
| `workflows` | List all supported agent workflows |

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

Three-tier NL summaries act as a semantic navigation layer:

- **File summaries**: purpose, responsibilities, side effects, dependencies
- **Symbol summaries**: 1-2 sentence descriptions for key classes/functions
- **Directory summaries**: folder-level role and contents overview

Summaries are generated from deterministic static analysis (tree-sitter, import graph, docstrings, call edges) by default. Use `--llm-summaries` to enrich file-level summaries with gpt-4o-mini for richer purpose and responsibility descriptions:

```bash
codebase-agent summarize /path/to/repo --llm-summaries
```

LLM summaries are batched (5 files per API call) and cached by file content hash -- only new or changed files are re-summarized. If the API key is missing or a batch fails, the system falls back to heuristic summaries automatically.

Configure the LLM model and batch size via environment variables:

```bash
SUMMARY_LLM_MODEL=gpt-4o-mini   # model for summary generation
SUMMARY_BATCH_SIZE=5             # files per LLM batch call
```

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
- **Summaries are coarse navigation, not final answers**: the agent verifies with symbol tools

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
