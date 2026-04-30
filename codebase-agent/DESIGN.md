# Design Document: RLM Dual-Mode Codebase Navigation Agent

## Overview

This document records the architecture decisions, tradeoffs, and justifications for the RLM (Recursive Language Model) dual-mode engine that powers this codebase navigation agent. It explains what we built, what inspired our choices, what we deliberately deferred, and when those deferred items should be revisited.

## Problem Statement

Standard approaches to codebase Q&A suffer from fundamental limitations:

- **RAG (Retrieval-Augmented Generation)**: Blindly chunks code into a vector database, losing structural hierarchy. Cannot follow import chains, call graphs, or understand module boundaries.
- **Long-context stuffing**: Loading entire codebases into massive context windows causes "lost in the middle" degradation and prohibitive token costs.
- **Deterministic playbooks**: Hardcoded step sequences per question type cannot adapt to novel or cross-cutting queries.

The RLM approach (arXiv 2512.24601) solves this by treating the codebase as an **external environment** that the LLM actively explores via tools and code execution, rather than passive context.

## Architecture: Two Execution Modes

We implement two configurable modes, selectable via `--mode adaptive|rlm`:

### Option A: Adaptive Engine (default)

The LLM receives structured tool schemas and picks which tool to call next. Each action is a discrete, observable `tool_call` → `tool_result` pair.

- **Invocation**: Standard OpenAI function calling (`tools=[...]` parameter)
- **Observability**: Every tool call is explicitly logged
- **Limitations**: Agent can ONLY use the 15 pre-built tools; no custom logic
- **Cost**: 1 LLM call per tool selection step
- **Best for**: Simple to moderate questions (Tier 1-4)

### Option B: RLM Engine

The LLM writes arbitrary Python code executed in a REPL sandbox. It has unrestricted access to the index, tools, standard library, and sub-model delegation.

- **Invocation**: Wraps the official `rlms` library (MIT, pip install rlms)
- **Observability**: Multi-layer tracing (instrumented tools + proxy index + trajectory logger)
- **Limitations**: Higher cost, requires sandbox security consideration
- **Cost**: Multiple LLM calls (root iterations + sub-model workers)
- **Best for**: Complex, novel, or cross-cutting questions that no single tool answers

## What We Implemented (and Why)

### 1. Two modes, not three

We removed the old deterministic playbook engine entirely. Both modes are LLM-driven.

**Justification**: The playbook engine used hardcoded `_exec_*` methods per workflow type. It could not adapt to novel questions and fell back to `FEATURE_EXPLANATION` at 0.3 confidence for anything it couldn't classify. LLM-driven execution handles all question types naturally.

### 2. Official `rlms` library for Option B

Instead of building our own REPL sandbox and sub-model orchestration, we wrap the MIT `rlms` package.

**Justification**: The library is battle-tested by the paper's authors, handles sandbox execution (local + Docker), manages the iteration loop and sub-model spawning, and provides trajectory logging. Building this from scratch would duplicate ~2000 lines of infrastructure with no added value.

### 3. Observer-pattern critic for tool validation (from AutoAgents)

When the agent proposes a new learned tool, an independent `gpt-4o-mini` call judges it on correctness, generalizability, non-redundancy, and safety before promotion.

**Justification**: Test cases alone are insufficient — the agent writes both the tool and the tests, so it can "grade its own homework." An independent critic (the AutoAgents Observer pattern) provides an unbiased quality gate. Using `gpt-4o-mini` (different model size) adds independence cheaply without needing a dedicated evaluation model.

### 4. Skill compositionality (from Voyager)

Learned tools can call other learned tools, enabling increasingly complex abstractions.

**Justification**: Voyager demonstrated that compositional skill libraries compound capability over time. A tool like `trace_model_to_api(model_name)` naturally builds on simpler tools like `find_model_files(model_name)` and `find_references(symbol)`. Without compositionality, each tool is isolated and the library's value plateaus.

### 5. Multi-layer tracing

Three layers of observability for Option B:
- Layer 1: Instrumented tool wrappers (logs every `tools.*` call)
- Layer 2: TracedRepoIndex proxy (logs direct index access)
- Layer 3: RLMLogger bridge (captures full REPL trajectory)

**Justification**: In Option A, tracing is trivial (discrete tool calls). In Option B, the agent writes free-form code mixing tool calls, direct index access, and computation. Without multi-layer tracing, you'd have no visibility into what the agent actually did — making debugging, cost attribution, and quality assessment impossible.

### 6. Configurable sandbox (local/Docker)

`--sandbox local` for fast development, `--sandbox docker` for isolated production.

**Justification**: The RLM agent generates and executes arbitrary Python code. In development (controlled prompts, local machine), direct `exec()` is fast and sufficient. In production or shared environments, Docker isolation prevents any rogue code from affecting the host. The cost is ~200ms overhead per execution in Docker mode.

### 7. Usage telemetry on learned tools

Track which tools get used, for which question types, and how often.

**Justification**: This provides a lightweight reinforcement signal without needing a formal reward model. Tools that are never used get evicted (LRU). Tools used frequently for specific question types can be prioritized in future retrievals. It's the minimum viable "memory" the system needs to improve over time.

## What We Deferred (and Why It's Overkill Now)

| Deferred Item | What It Is | Why We Skipped It | When to Revisit |
|---|---|---|---|
| Embedding-based skill retrieval | Vector search over tool descriptions (Voyager uses this) | We'll have 5-20 tools per codebase; a flat list in the system prompt works fine. Adding embeddings requires a vector store dependency for marginal gain. | When the learned tool library exceeds 50+ tools per codebase, or when building a shared global skill library across users. |
| Prometheus-Eval / TruLens | Dedicated LLM-as-a-judge libraries with custom rubrics and evaluation models | A single `gpt-4o-mini` critic call achieves the same result without adding library dependencies or hosting a 7B evaluation model. | When you need batch evaluation of hundreds of proposed tools, or when you want the judge to be a fundamentally different model family for independence. |
| AST-level code instrumentation (Layer 4) | Parse generated code with `ast` module and inject logging at every function call node | Layers 1-3 provide sufficient observability for debugging and cost tracking. AST instrumentation adds complexity and performance overhead for marginal additional insight. | When you need per-line cost attribution or fine-grained performance profiling of generated code. |
| Full AutoAgents multi-observer pattern | Three separate observer roles (Agent Observer, Plan Observer, Action Observer) evaluating different aspects | One observer (tool quality critic) covers our validation needs. The agent's "plan" is implicit in its code, and "action" results are verified by test cases. | When learned tools start having multi-step execution plans that need plan-level review, or when the system is deployed multi-tenant with stricter quality requirements. |
| ColBERT embeddings for skill indexing | Late-interaction embedding model for semantic skill search (used by code-voyager) | Requires hosting a ColBERT model, building an index, and maintaining it. Overkill for <50 tools where keyword matching on descriptions suffices. | When shared skill libraries span multiple codebases and users, requiring cross-domain retrieval. |
| Custom REPL sandbox (built from scratch) | Our own restricted `exec()` environment with custom builtins | The `rlms` library already provides a tested sandbox implementation with configurable isolation (local, Docker, Modal, E2B). No reason to rebuild. | Never, unless the `rlms` library is abandoned or has fundamental limitations we can't work around. |
| Deterministic playbook mode | The original hardcoded `_exec_*` workflow executors | Both modes are LLM-driven. Playbooks were too rigid for novel questions and required maintaining 24 separate executor functions. | Never. This is a permanent architectural decision. The playbook definitions remain as reference material for system prompts. |

## Research Inspirations

### RLM Paper (arXiv 2512.24601)

**Core contribution**: Teach LLMs to manage their own context by writing code in a REPL, rather than receiving everything in the prompt.

**What we adopted**: Root Model + REPL environment + Sub-Model workers architecture. The codebase is loaded as programmatic data, not prompt context. The model writes exploration code iteratively.

### Voyager (Wang et al., 2023)

**Core contribution**: Lifelong learning agent that stores executable skills, retrieves them semantically, verifies them with a critic, and composes complex behaviors from simpler ones.

**What we adopted**: Skill library as executable code (not descriptions), self-verification before promotion, compositionality (skills calling skills).

**What we deferred**: Embedding-based retrieval (overkill at our scale), automatic curriculum generation (not applicable to Q&A).

### AutoAgents (Chen et al., 2024 / IJCAI)

**Core contribution**: Dynamic generation of specialized agents with Observer roles that independently evaluate quality.

**What we adopted**: The Observer pattern — an independent LLM critic that evaluates proposed tools on a structured rubric before promotion.

**What we deferred**: Multi-observer architecture (3 roles), dynamic agent generation (we have fixed modes), collaborative refinement between observers.

### code-voyager (zenbase)

**Core contribution**: Practical port of Voyager's skill library to codebase navigation (for Claude Code). Validates that the approach works in this domain.

**What we adopted**: Confirmation that per-codebase skill storage, session-persistent memory, and SKILL.md metadata files are viable patterns.

**What we deferred**: ColBERT-based skill retrieval, Claude Code hook integration (we use CLI + OpenAI).

## Tradeoffs Summary

| Decision | Benefit | Cost |
|---|---|---|
| LLM-driven tool selection (Option A) | Handles novel questions; no classifier maintenance | ~$0.01-0.05 per query in LLM calls |
| Unrestricted REPL (Option B) | Maximum flexibility; cross-tool logic; sub-model parallelism | Higher cost (~$0.05-0.20); sandbox security needed |
| Single critic (not 3 observers) | Simple, cheap, sufficient validation | Might miss plan-level issues in complex tools |
| No embedding retrieval | Zero setup; works at current scale | Won't scale past ~50 tools without friction |
| `rlms` library dependency | Free REPL + sub-model infra | Coupled to MIT library's API stability |
| Removing playbook mode | Simpler codebase; unified LLM-driven approach | Lose guaranteed-fast deterministic paths for simple lookups |
