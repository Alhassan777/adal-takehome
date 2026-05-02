# Workflows

The workflow subsystem is the brain of the codebase agent. It classifies user
questions via a small LLM call, injects a playbook-guided strategy hint into
the prompt, runs LLM-driven tool loops, and returns structured answers.

## Architecture

```
User question
      |
      v
 classifier.py  -- one OPENAI_SUB_MODEL call --> WorkflowType + confidence
      |
      v
 adaptive_engine.py / rlm_engine.py
      |  (playbook strategy, tools, budget, failure chains
      |   injected as a second system message)
      |
      +---> AdaptiveEngine  (OpenAI function-calling loop, playbook.max_tool_rounds)
      +---> RLMEngine        (Python REPL loop, MAX_RLM_ITERATIONS)
```

Both engines share the same 15-tool registry, tracing infrastructure, and
result schema. The choice between them is set via the `EXECUTION_MODE`
environment variable (`adaptive` or `rlm`).

## Modules

| File | Purpose |
|---|---|
| `types.py` | `WorkflowType` enum (23 types across 6 tiers) and `TIER_MAP` |
| `classifier.py` | LLM-based classifier using `OPENAI_SUB_MODEL` -- sends all 23 workflow types with trigger descriptions, returns `ClassificationResult` or `None` on failure |
| `playbooks.py` | Declarative playbooks per workflow type (strategy steps, required tools, budgets, failure chains); injected into the adaptive engine prompt by `_build_strategy_hint()` |
| `engine.py` | `create_engine()` factory and `build_tool_registry()` shared across modes |
| `adaptive_engine.py` | **Adaptive mode** -- classifies the question, injects playbook hint, LLM picks tools via OpenAI function calling; budget set by `playbook.max_tool_rounds` (falls back to `MAX_ADAPTIVE_ROUNDS = 15`) |
| `rlm_engine.py` | **RLM mode** -- LLM writes Python executed in a REPL namespace; up to `MAX_RLM_ITERATIONS` (10) turns |
| `tool_schemas.py` | OpenAI function-calling JSON schemas and human-readable signature text for the 15 built-in tools |
| `tool_reflector.py` | Post-answer reflection that proposes reusable tools from RLM conversations |
| `learned_tools.py` | Persistent learned-tool registry with two-stage validation (deterministic + LLM critic) and LRU eviction |
| `tracing.py` | Three-layer tracing: instrumented tool wrappers, `TracedRepoIndex` proxy, `DevLoggerBridge` |
| `query_context.py` | Builds the user message from `ParsedQuery`, including `@`-mentioned file context |

## Execution modes

### Adaptive (`AdaptiveEngine`)

The LLM decides which tools to call on each turn using OpenAI's
function-calling API. The engine:

1. Classifies the question via `classify_question()` (one `OPENAI_SUB_MODEL`
   call). If it fails, falls back to the generic prompt.
2. Looks up the matching playbook and injects its strategy, required tools,
   failure chains, and budget as a second system message.
3. Sends the system prompt(s) + user message.
4. If the model returns `tool_calls`, executes them and appends one assistant
   message followed by N tool-result messages.
5. Loops until the model returns `finish_reason="stop"` or
   `playbook.max_tool_rounds` is exhausted.

Best for: straightforward lookup/analysis questions where the built-in tool set
is sufficient.

### RLM (`RLMEngine`)

The LLM writes arbitrary Python that runs in a sandboxed REPL namespace
containing `tools.*`, `index`, `sub_call`, and standard-library modules. The
engine:

1. Sends the system prompt (with tool signatures) + user message.
2. Executes the returned code block, captures stdout.
3. Feeds the output back as a user message and loops.
4. Terminates when `answer["ready"] = True` or the iteration budget is
   exhausted.

After answering, a `ToolReflector` reviews the conversation and may propose
reusable tools for the learned-tool library.

Best for: complex analytical questions that benefit from custom code, data
aggregation, or sub-model delegation.

## Workflow classification

Every question is classified into one of 23 workflow types via a single
`OPENAI_SUB_MODEL` call. The classifier prompt lists all types with their
`trigger_description` (sourced from `playbooks.py`) and asks the model to pick
the best match. Returns `None` on any failure so the engine can fall back to
the generic prompt.

## Workflow taxonomy (6 tiers)

| Tier | Category | Types | Playbook budget |
|------|----------|-------|-----------------|
| 1 | Direct Lookup | `symbol_lookup`, `file_reading`, `file_listing`, `text_search` | 2-3 rounds |
| 2 | Navigational | `goto_definition_hint`, `goto_definition_no_hint`, `goto_definition_no_file`, `import_tracing`, `reverse_import_tracing` | 3-4 rounds |
| 3 | Analytical | `feature_explanation`, `impact_analysis`, `test_discovery`, `call_graph`, `reverse_call_graph` | 4-8 rounds |
| 4 | Structural | `module_overview`, `architecture_map`, `api_surface`, `dependency_graph` | 4-6 rounds |
| 5 | Change-Oriented | `safe_refactoring`, `dead_code`, `missing_tests`, `breaking_change` | 4-6 rounds |
| 6 | Contextual | `follow_up`, `comparison`, `explicit_context` | 4-5 rounds |

## Learned tools

RLM mode supports a Voyager-inspired learned-tool library:

1. After answering, `ToolReflector` proposes reusable functions extracted from
   the REPL conversation.
2. The user approves or skips each proposal via the CLI.
3. Approved tools pass two-stage validation: deterministic (compile + test
   cases) then LLM critic (correctness, generalizability, safety).
4. Promoted tools persist to `.cache/learned_tools/` and are injected as
   `learned_*` functions in future sessions.
5. LRU eviction kicks in when the tool count exceeds 20.

Tool names are validated against a strict `[a-z][a-z0-9_]{0,63}` pattern and
file paths are checked to stay inside the tools directory.

## Tool registry (15 built-in tools)

All tools accept keyword arguments and return JSON-serializable dicts:

- `search_symbols_tool` -- symbol name search across the index
- `search_text_tool` -- ripgrep-powered regex search in files
- `get_definition` -- resolve a symbol to its definition (LSP or tree-sitter)
- `find_references` -- all references to a symbol
- `read_snippet` -- read lines from a file
- `get_imports` -- list imports for a file
- `trace_module` -- forward/reverse dependency info for a file
- `get_call_graph` -- outgoing calls from a function
- `find_tests` -- test files covering a file or symbol
- `impact_analysis` -- change-impact assessment for a symbol
- `get_file_summary` -- NL summary of a file
- `search_summaries` -- keyword search across file summaries
- `get_directory_summary` -- NL summary of a directory
- `list_tree` -- compact directory tree of the repo
- `repo_map` -- hierarchical annotated repository map

## Configuration

Key constants in `config.py`:

| Constant | Default | Description |
|---|---|---|
| `EXECUTION_MODE` | `adaptive` | Engine mode (`adaptive` or `rlm`) |
| `OPENAI_MODEL` | `gpt-4o` | Primary LLM for both engines |
| `OPENAI_SUB_MODEL` | `gpt-4o-mini` | Worker model for classifier, sub-calls, and critic |
| `MAX_ADAPTIVE_ROUNDS` | 15 | Fallback max turns when no playbook is available |
| `MAX_RLM_ITERATIONS` | 10 | Max REPL iterations in RLM mode |
| `MAX_SUB_MODEL_DEPTH` | 2 | Max recursion for `sub_call` |
| `MAX_LEARNED_TOOLS` | 20 | Cap before LRU eviction |

## Tests

- `tests/test_workflows.py` -- classifier, playbooks, learned-tool name validation
- `tests/test_engine_modes.py` -- engine factory, adaptive/RLM answer loops, budget exhaustion, error branches
- `tests/test_tool_suggestion_flow.py` -- RLM tool reflection + CLI approval flow
- `tests/test_learned_tools.py` -- deterministic validation, critic, promotion lifecycle, eviction
