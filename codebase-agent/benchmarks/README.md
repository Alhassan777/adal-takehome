# Benchmark Evaluation Harness

Automated evaluation of the codebase navigation agent against four benchmarks, with a 5-configuration ablation matrix.

## Benchmarks

| Benchmark | What it tests | Tasks | Metric |
|-----------|---------------|-------|--------|
| **RepoQA** | Function localization via natural-language description | 100 (Python) | Pass rate (BLEU > 0.8) |
| **SWE-QA** | Repository-level code question answering | 720 (15 repos) | Avg score /100 (LLM judge) |
| **DependEval** | Dependency ordering recognition | Variable (Python subset) | Exact Match Rate |
| **Synthetic** | All agent capabilities via hand-crafted repos with known answers | 50 repos, ~280 questions | Pass rate + avg score |

## Ablation Matrix

| Config | Mode | LSP | Summaries | Tests |
|--------|------|-----|-----------|-------|
| `full_adaptive` | adaptive | on | on | Best-case |
| `full_rlm` | rlm | on | on | Mode comparison |
| `no_lsp` | adaptive | off | on | LSP contribution |
| `no_summaries` | adaptive | on | off | Summaries contribution |
| `minimal` | adaptive | off | off | Baseline |

## Quick Start

```bash
# Install benchmark dependencies
pip install -r benchmarks/requirements.txt

# Run RepoQA with default config (full_adaptive), limit to 5 tasks
python -m benchmarks.run_all run --benchmark repoqa --config full_adaptive --max-tasks 5

# Run all configs on RepoQA
python -m benchmarks.run_all run --benchmark repoqa --all-configs

# Run SWE-QA on small repos only
python -m benchmarks.run_all run --benchmark sweqa --repos flask,requests,pytest

# Run synthetic with specific challenges and sizes
python -m benchmarks.run_all run --benchmark synthetic --challenges basic_nav,name_collision --sizes XS,S --max-tasks 10

# Run synthetic on all challenges at XS size (fast smoke test)
python -m benchmarks.run_all run --benchmark synthetic --sizes XS

# Run everything
python -m benchmarks.run_all run --all

# Generate report from latest results
python -m benchmarks.report generate --latest
```

## Output Structure

```
benchmarks/results/{timestamp}/
  repoqa/
    full_adaptive.jsonl
    full_adaptive_metrics.json
    ...
  sweqa/
    ...
  dependeval/
    ...
  synthetic/
    full_adaptive.jsonl
    full_adaptive_metrics.json
    ...
  summary.json
  report.md
```

## Synthetic Benchmark

The synthetic benchmark generates Python repos from scratch with known-correct answers for every question. No external datasets or network access required.

### Challenge Types (10)

| Challenge | What it tests | Agent workflows exercised |
|-----------|---------------|---------------------------|
| `basic_nav` | Symbol lookup, file listing, text search | SYMBOL_LOOKUP, FILE_LISTING, TEXT_SEARCH |
| `import_chains` | Re-exports, aliases, relative/circular imports | IMPORT_TRACING, GOTO_DEFINITION_HINT |
| `deep_hierarchy` | Navigation through deeply nested packages | MODULE_OVERVIEW, ARCHITECTURE_MAP |
| `name_collision` | Disambiguation when same name appears in N files | GOTO_DEFINITION (all variants) |
| `inheritance` | Class hierarchies, MRO, method overrides | CALL_GRAPH, FEATURE_EXPLANATION |
| `dependency` | Linear chains, diamonds, fan-out hubs | DEPENDENCY_GRAPH, IMPACT_ANALYSIS, BREAKING_CHANGE |
| `test_mapping` | Co-located tests, separate tree, missing coverage | TEST_DISCOVERY, MISSING_TESTS |
| `dead_code` | Unused symbols, transitively dead code | DEAD_CODE, SAFE_REFACTORING |
| `cross_cutting` | Decorators, plugin registries, dynamic dispatch | FEATURE_EXPLANATION, CALL_GRAPH |
| `api_surface` | `__all__`, underscore conventions, re-exports | API_SURFACE, MODULE_OVERVIEW |

### Size Tiers (5)

| Tier | Files | Lines | Purpose |
|------|-------|-------|---------|
| XS | 3-15 | 50-200 | Sanity / smoke test |
| S | 10-20 | 200-500 | Small project baseline |
| M | 24-35 | 700-2000 | Realistic project |
| L | 37-90 | 1700-6600 | Stress test |
| XL | 62-210 | 2700-14000 | Scaling limit test |

### CLI Options

```bash
--benchmark synthetic      # Select synthetic benchmark
--challenges basic_nav,... # Comma-separated subset (default: all 10)
--sizes XS,S,...           # Comma-separated subset (default: all 5)
--max-tasks N              # Cap total questions evaluated
```

### Scoring Methods

Each question uses one of these automated scorers:

- **file_and_symbol_match**: Correct file path + symbol name in answer
- **file_set_match**: F1 recall over expected file set
- **ordered_list_match**: Files appear in correct dependency order
- **symbol_set_match**: Correct set of symbols mentioned
- **risk_level_match**: Correct risk assessment (high/medium/low)
- **contains_keywords**: Required keywords present in explanation
- **boolean_match**: Correct yes/no or count answer

## Adding a New Benchmark

1. Create `benchmarks/{name}_eval.py` with:
   - `run_{name}_evaluation(config, max_tasks, progress_callback) -> list[Result]`
   - `compute_metrics(results) -> dict`
2. Add the benchmark name to `BENCHMARKS` in `run_all.py`
3. Add a `_run_{name}()` dispatcher in `run_all.py`

## Cost Estimation

| Benchmark | Tasks | Tokens/task (est.) | Full matrix cost (GPT-4o) |
|-----------|-------|-------------------|--------------------------|
| RepoQA | 100 | ~50K | ~$25 |
| SWE-QA (3 repos) | 144 | ~100K | ~$72 |
| SWE-QA (all) | 720 | ~100K | ~$360 |
| DependEval | ~200 | ~20K | ~$20 |
| Synthetic (XS only) | ~55 | ~15K | ~$4 |
| Synthetic (all sizes) | ~280 | ~30K | ~$42 |

Use `--max-tasks N` for budget-constrained runs. Use `OPENAI_MODEL=gpt-4o-mini` for cheaper iterations.
