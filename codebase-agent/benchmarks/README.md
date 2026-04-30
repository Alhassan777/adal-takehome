# Benchmark Evaluation Harness

Automated evaluation of the codebase navigation agent against three benchmarks, with a 5-configuration ablation matrix.

## Benchmarks

| Benchmark | What it tests | Tasks | Metric |
|-----------|---------------|-------|--------|
| **RepoQA** | Function localization via natural-language description | 100 (Python) | Pass rate (BLEU > 0.8) |
| **SWE-QA** | Repository-level code question answering | 720 (15 repos) | Avg score /100 (LLM judge) |
| **DependEval** | Dependency ordering recognition | Variable (Python subset) | Exact Match Rate |

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
    full_adaptive.jsonl
    full_adaptive_metrics.json
    ...
  dependeval/
    full_adaptive.jsonl
    full_adaptive_metrics.json
    ...
  summary.json
  report.md
```

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

Use `--max-tasks N` for budget-constrained runs. Use `OPENAI_MODEL=gpt-4o-mini` for cheaper iterations.
