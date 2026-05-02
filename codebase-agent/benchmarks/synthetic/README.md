# Synthetic Benchmark Suite

A fully self-contained benchmark framework for evaluating the codebase navigation agent. Every test repository is **generated in code** — no external datasets, no cloning, no internet access required. Each generated project comes with questions whose correct answers are known ahead of time.

---

## How It Works

```
repos.py          ← registry of all 55 (11 challenges × 5 sizes) repo specs
generator.py      ← core data types and shared code-generation helpers
eval.py           ← runs the agent against a repo, scores each answer
challenges/       ← 11 independent challenge modules (see challenges/README.md)
```

The evaluation loop for each question is:

1. `repos.py` is asked for a `(challenge, size)` pair.
2. The matching `challenges/*.py` module builds a `SyntheticRepo` — a dict of file contents plus a list of `GroundTruthQuestion` objects with known-correct answers.
3. `generator.write_repo()` materializes the files in a temp directory and writes a `ground_truth.json` alongside them.
4. `eval.py` calls `run_agent()` once per question and captures the answer.
5. The answer is routed to the appropriate scorer function.
6. `generator.cleanup_repo()` deletes the temp directory.
7. Results are collected into `SyntheticResult` objects and aggregated by `compute_metrics()`.

---

## `generator.py` — Core Framework

The foundation every challenge module builds on.

### Data types

| Symbol | Purpose |
|---|---|
| `SizeTier` | Enum: `XS / S / M / L / XL` — controls file count and line counts |
| `ScoringMethod` | Enum of 7 scoring strategies (see table below) |
| `Difficulty` | Enum: `easy / medium / hard` — metadata, not used for filtering |
| `GroundTruthQuestion` | Dataclass: `id`, `question`, `workflow_type`, `expected`, `scoring`, `difficulty` |
| `SyntheticRepo` | Dataclass: holds `files` dict and `questions` list; exposes `file_count` and `total_lines` |

### Lifecycle functions

| Function | Purpose |
|---|---|
| `write_repo(repo, target_dir?)` | Materializes all files + `ground_truth.json` in a temp or named directory |
| `cleanup_repo(repo_dir)` | Deletes the materialized directory |

### Code-generation helpers

| Function | Purpose |
|---|---|
| `_pad_with_helpers(src, n, prefix)` | Pads a file to `n` lines by appending filler helper functions — used by every challenge to scale to larger size tiers |
| `_make_class(name, bases?, methods?, docstring?)` | Generates a class definition string |
| `_make_function(name, params?, body?, docstring?)` | Generates a function definition string |

### Size tiers

| Tier | Target Files | Approx. Lines |
|---|---|---|
| XS | 3–5 | ~50–100 |
| S | 10–15 | ~300–500 |
| M | 30–50 | ~1,500–3,000 |
| L | 80–120 | ~5,000–10,000 |
| XL | 200+ | ~15,000+ |

### Scoring methods

| Method | What it checks |
|---|---|
| `FILE_AND_SYMBOL_MATCH` | Answer mentions the correct file **and** symbol name (0.5 pts each) |
| `FILE_SET_MATCH` | Recall over a set of expected files |
| `ORDERED_LIST_MATCH` | Files appear in the correct order in the answer |
| `SYMBOL_SET_MATCH` | Recall over a set of expected symbol names |
| `RISK_LEVEL_MATCH` | Answer contains the expected risk level (`high`, `medium`, `low`) |
| `CONTAINS_KEYWORDS` | Recall over a list of required keywords |
| `BOOLEAN_MATCH` | Flexible check for yes/no, existence, or count questions |

A question **passes** when its score is ≥ 0.5.

---

## `repos.py` — Challenge Registry

Registers all 11 challenge modules and exposes helper functions to the rest of the harness. Repos are generated **lazily** — importing `repos.py` is instant; cost is only paid when `generate_repo()` is called.

| Symbol | Purpose |
|---|---|
| `CHALLENGES` | Dict mapping challenge name → `generate(size)` callable |
| `ALL_SIZES` | All five `SizeTier` values |
| `generate_repo(challenge, size)` | Generate one `SyntheticRepo` by name and size |
| `generate_all(challenges?, sizes?)` | Generate the full matrix or a named slice |
| `list_repo_ids()` | Returns all 55 `"{challenge}_{size}"` IDs |
| `challenge_names()` | Returns the 11 challenge key strings |

---

## `eval.py` — Evaluation Driver

Bridges the agent runner and the scoring functions.

| Symbol | Purpose |
|---|---|
| `SyntheticResult` | Result for one question: score, pass/fail, answer excerpt, timing, error |
| `evaluate_question(repo_dir, repo, question, config)` | Runs the agent once and scores the answer |
| `evaluate_repo(repo, config, progress_callback?)` | Evaluates all questions for one repo, sharing a session |
| `run_synthetic_evaluation(config, challenges?, sizes?, max_tasks?)` | Top-level driver — iterates the matrix, writes and cleans each temp repo |
| `compute_metrics(results)` | Aggregates results into pass rates, avg scores, per-challenge and per-scoring-method breakdowns |

### Metrics produced by `compute_metrics()`

| Key | Description |
|---|---|
| `pass_rate` | Fraction of questions with score ≥ 0.5 |
| `avg_score` | Mean score across all questions (0.0–1.0) |
| `total` / `passed` / `errors` | Counts |
| `avg_duration_s` | Mean per-question agent latency |
| `by_challenge` | Per-challenge pass rate and avg score |
| `by_scoring_method` | Per-scoring-method breakdown |

---

## Running the Suite

The synthetic suite plugs into `benchmarks/run_all.py`. To run it via the CLI:

```bash
# Run all 11 challenges × 5 sizes with the default config
python -m benchmarks.run_all --benchmark synthetic

# Narrow to specific challenges and size tiers
python -m benchmarks.run_all --benchmark synthetic \
    --challenges basic_nav,dependency,dead_code \
    --sizes XS,S

# Run all 5 ablation configs
python -m benchmarks.run_all --benchmark synthetic --all-configs

# Smoke test — 20 questions only
python -m benchmarks.run_all --benchmark synthetic --max-tasks 20
```

To use the suite directly in Python:

```python
from codebase_agent.benchmarks.configs import get_config
from codebase_agent.benchmarks.synthetic.eval import run_synthetic_evaluation, compute_metrics

config = get_config("full_adaptive")
results = run_synthetic_evaluation(
    config,
    challenges=["basic_nav", "dependency"],   # omit to run all 11
    sizes=["XS", "S"],                         # omit to run all 5 sizes
    max_tasks=50,                              # omit for the full run
)
print(compute_metrics(results))
```

To generate and inspect a repo without running the agent:

```python
from codebase_agent.benchmarks.synthetic.repos import generate_repo
from codebase_agent.benchmarks.synthetic.generator import SizeTier, write_repo

repo = generate_repo("cross_cutting", SizeTier.S)
print(repo.file_count, "files,", repo.total_lines, "lines")
path = write_repo(repo)   # materializes to a temp directory
print("Written to", path)
```

---

## Challenge Reference

See [`challenges/README.md`](challenges/README.md) for the full description of all 11 challenges — what each one tests, the synthetic repo structure it creates, and every question it asks.
