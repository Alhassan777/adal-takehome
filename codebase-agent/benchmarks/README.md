# Benchmarks

This directory contains the full evaluation harness for the codebase navigation agent. It runs the agent across four benchmark suites under five ablation configurations and writes structured results to `results/`.

---

## Directory Layout

```
benchmarks/
├── README.md               ← this file
├── __init__.py
├── __main__.py             ← enables `python -m benchmarks.run_all`
├── run_all.py              ← CLI entry point (Typer app)
├── configs.py              ← ablation matrix (5 configs)
├── runner.py               ← core agent invocation wrapper
├── repoqa_eval.py          ← RepoQA adapter
├── sweqa_eval.py           ← SWE-QA adapter
├── dependeval_eval.py      ← DependEval adapter
├── synthetic/              ← self-contained synthetic benchmark suite
│   └── README.md           ← synthetic-specific docs
├── vendor/                 ← external datasets cloned on first run
│   ├── repoqa_data/
│   ├── repoqa_repos/
│   ├── SWE-QA-Bench/
│   └── DependEval/
└── results/                ← created at runtime
    └── YYYY-MM-DD_HH-MM-SS/
        ├── summary.json
        ├── repoqa/{config_id}.jsonl + {config_id}_metrics.json
        ├── sweqa/{config_id}.jsonl  + {config_id}_metrics.json
        ├── dependeval/{config_id}.jsonl + {config_id}_metrics.json
        └── synthetic/{config_id}.jsonl + {config_id}_metrics.json
```

---

## Quick Start

```bash
# Single benchmark, default config (full_adaptive)
python -m benchmarks.run_all --benchmark synthetic

# Single benchmark, specific config
python -m benchmarks.run_all --benchmark repoqa --config full_rlm

# Single benchmark, all 5 ablation configs
python -m benchmarks.run_all --benchmark dependeval --all-configs

# All 4 benchmarks × all 5 configs (full ablation matrix)
python -m benchmarks.run_all --all

# Smoke test — 10 tasks only
python -m benchmarks.run_all --benchmark synthetic --max-tasks 10

# Synthetic: narrow to specific challenges and size tiers
python -m benchmarks.run_all --benchmark synthetic \
    --challenges basic_nav,dependency \
    --sizes XS,S

# SWE-QA: narrow to specific repos
python -m benchmarks.run_all --benchmark sweqa --repos flask,requests
```

Every run creates a timestamped directory under `results/` and writes a `summary.json` with a table of all metrics.

---

## Ablation Configs (`configs.py`)

The ablation matrix tests how much each component of the agent contributes to performance by selectively disabling features.

| Config ID | Mode | LSP | Summaries | Purpose |
|---|---|---|---|---|
| `full_adaptive` | ADAPTIVE | ✓ | ✓ | Best-case adaptive — all features on (default) |
| `full_rlm` | RLM | ✓ | ✓ | Best-case retrieval-augmented loop — all features on |
| `no_lsp` | ADAPTIVE | ✗ | ✓ | Adaptive without Pyright LSP — measures LSP contribution |
| `no_summaries` | ADAPTIVE | ✓ | ✗ | Adaptive without NL summaries — measures summary contribution |
| `minimal` | ADAPTIVE | ✗ | ✗ | Baseline — tree-sitter + ripgrep only |

`AblationConfig` is a frozen dataclass; `ALL_CONFIGS` is a list of all five for looping. `get_config("full_adaptive")` retrieves by string or `ConfigID` enum.

---

## Core Runner (`runner.py`)

A thin wrapper that every benchmark adapter uses. It handles session initialization, engine creation, timing, and error capture so each adapter only needs to supply `(repo_path, question, config)`.

### `RunResult`

Returned by every agent invocation:

| Field | Type | Description |
|---|---|---|
| `question` | str | The question asked |
| `answer` | str | Agent's full response text |
| `config_id` | str | Which ablation config was used |
| `repo_path` | str | Path to the repo that was indexed |
| `duration_s` | float | Wall-clock time in seconds |
| `success` | bool | `False` if the agent raised an exception |
| `tool_calls` | list[dict] | Tool calls the engine made |
| `error` | str \| None | Exception message + traceback if `success=False` |

### Key Functions

**`init_session_for_config(repo_path, config)`** — creates or retrieves a cached `Session` for a given `(repo, config)` pair. Calling this separately before a batch avoids re-indexing the same repo for every question.

**`run_agent(repo_path, question, config, session?)`** — runs the agent on a single question. Accepts an optional pre-initialized session to skip re-init overhead. Always returns a `RunResult`, never raises.

**`run_batch(repo_path, questions, config, progress_callback?)`** — initializes the session once, then calls `run_agent` for each question in the list. Preferred over calling `run_agent` in a loop when all questions target the same repo.

---

## Benchmark Adapters

### `repoqa_eval.py` — RepoQA

**What it tests:** Given only a natural-language description of a function, can the agent navigate a real GitHub repository and return the correct source code?

**Task format:** "Find the function described below and return its exact source code."

**Dataset:** [evalplus/repoqa](https://github.com/evalplus/repoqa) — Python subset. Loaded via the `repoqa` pip package, HuggingFace `datasets`, or a local JSONL cache at `vendor/repoqa_data/python.jsonl`. Repositories are shallow-cloned into `vendor/repoqa_repos/` on first use.

**Scoring:** BLEU-4 between the agent's extracted code block and the ground-truth function body. A task **passes** at BLEU ≥ 0.8. `extract_code_block()` extracts the first fenced code block from the agent's response; falls back to heuristic `def`-line extraction.

**Key metrics output:**

| Metric | Description |
|---|---|
| `pass_rate` | Fraction of tasks with BLEU ≥ 0.8 |
| `avg_bleu_score` | Mean BLEU-4 across all tasks |
| `avg_duration_s` | Mean per-task agent latency |
| `errors` | Tasks where the agent failed entirely |

---

### `sweqa_eval.py` — SWE-QA

**What it tests:** Broad repository-level comprehension — architecture questions, API usage, feature explanations — across 15 popular Python projects (720 QA pairs total, ~48 questions per repo).

**Task format:** "I have a code repository at {path}. Please answer the following question about this repository."

**Dataset:** [SWE-QA-Bench](https://github.com/peng-weihan/SWE-QA-Bench) — cloned into `vendor/SWE-QA-Bench/` on first use. Questions are loaded from `Experiment/datasets/questions/{repo}.jsonl`. Target repos are cloned at their pinned commits into `vendor/SWE-QA-Bench/datas/repos/`. Default repos: `flask`, `requests`, `pytest`.

**Scoring:** LLM-as-Judge across 5 dimensions (20 pts each, 100-pt total). The judge script writes scores to `results/sweqa_scoring/{config_id}/`. If the judge script is unavailable, a built-in heuristic scorer activates (keyword overlap + file reference detection + answer length).

**Scoring dimensions:**

| Dimension | Max | What it measures |
|---|---|---|
| `correctness` | 20 | Factual accuracy of the answer |
| `completeness` | 20 | Covers all relevant aspects |
| `relevance` | 20 | Stays on topic, grounded in the code |
| `clarity` | 20 | Clear and well-structured explanation |
| `reasoning` | 20 | Shows reasoning process |

**Key metrics output:**

| Metric | Description |
|---|---|
| `avg_score` | Mean total score out of 100 |
| `avg_{dimension}` | Mean score per dimension |
| `scored` | Number of tasks that received scores |
| `errors` | Agent failures |

---

### `dependeval_eval.py` — DependEval

**What it tests:** Strict dependency ordering — given a small Python project, output the files in topological order (leaf dependencies first, dependents last) as a JSON array.

**Task format:** "Output ONLY a JSON array of filenames in dependency order." The agent must produce a parseable `["utils.py", "models.py", "services.py", "main.py"]` style response.

**Dataset:** [DependEval](https://github.com/ink7-sudo/DependEval) Task 1 (Dependency Recognition), Python subset. Cloned into `vendor/DependEval/`. Supports multiple directory layouts the dataset may use; falls back to full directory scan if the expected paths differ between dataset versions.

**Evaluation flow:** Each task's files are written to a temp directory, indexed by the agent, and deleted afterward. `parse_predicted_order()` extracts the JSON array from the agent response.

**Scoring:** Exact match only — the predicted file ordering must be identical to the ground-truth list (after normalizing to basenames). Partial matches (correct set, wrong order) are counted separately in the metrics but do not count as passes.

**Key metrics output:**

| Metric | Description |
|---|---|
| `exact_match_rate` | Fraction of tasks with a perfectly correct ordering |
| `matched` | Count of exact matches |
| `partial_matches` | Correct file set but wrong order |
| `errors` | Agent failures |
| `avg_duration_s` | Mean per-task latency |

---

### `synthetic/` — Synthetic Suite

**What it tests:** 11 controlled challenge categories (basic navigation, import chains, inheritance, dead code, cross-cutting concerns, etc.) across 5 size tiers (XS → XL). Every question has a machine-verifiable ground-truth answer — no LLM judge required.

**Dataset:** Fully generated in code. No external data or cloning needed.

See [`synthetic/README.md`](synthetic/README.md) for the full description of all 11 challenges, their repo structures, and every question they ask.

**Key metrics output:**

| Metric | Description |
|---|---|
| `pass_rate` | Fraction of questions with score ≥ 0.5 |
| `avg_score` | Mean score across all questions (0.0–1.0) |
| `by_challenge` | Per-challenge pass rate and avg score |
| `by_scoring_method` | Per-scoring-method breakdown |
| `errors` | Agent failures |

---

## Results Structure

Each run writes to `results/YYYY-MM-DD_HH-MM-SS/`:

```
results/
└── 2026-05-01_17-30-00/
    ├── summary.json                        ← all metrics in one file
    ├── repoqa/
    │   ├── full_adaptive.jsonl             ← one JSON line per task
    │   ├── full_adaptive_metrics.json
    │   ├── full_rlm.jsonl
    │   └── full_rlm_metrics.json
    ├── sweqa/
    │   └── ...
    ├── dependeval/
    │   └── ...
    └── synthetic/
        └── ...
```

Each `.jsonl` file contains one result per line. The `summary.json` is a nested dict: `{benchmark: {config_id: metrics}}`, which is also printed as a Rich table at the end of every run.

---

## Adding a New Benchmark

1. Create `your_eval.py` in this directory.
2. Define `YourTask`, `YourResult` dataclasses with a `to_dict()` method.
3. Implement `run_your_evaluation(config, *, max_tasks?, progress_callback?) -> list[YourResult]`.
4. Implement `compute_metrics(results) -> dict`.
5. Add `"your_bench"` to `BENCHMARKS` in `run_all.py`.
6. Add a `_run_your_bench(config, run_dir, max_tasks)` private function following the pattern of the existing four.
7. Wire it into the `run()` command's dispatch block.

The adapter calls `run_agent()` from `runner.py` and produces `RunResult` objects — that's the only coupling to the core agent.
