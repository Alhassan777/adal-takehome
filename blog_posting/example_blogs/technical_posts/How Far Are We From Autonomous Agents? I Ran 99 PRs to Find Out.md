# How Far Are We From Autonomous Agents? I Ran 99 PRs to Find Out

*February 2, 2026 · 8 min read · Li Yin*

**Tags:** ai-agents, autonomous-agents, experiment, lessons-learned

I've been thinking about "fully autonomous agents" a lot lately. Everyone wants them. VCs fund them. Twitter hypes them.

But how close are we, really?

Last week, I decided to test my own assumptions. The hard way.

## The Experiment

- **Setup**: 1 autonomous long-running session. AdaL with Claude Opus 4.5. Zero human review.
- **Task**: Add AdaL to the "compatible agents" section of repos listed on skill.sh—a directory of AI coding skills and plugins.
- **Result**: 99 PRs created. And I pissed off a bunch of open source maintainers.

## The Numbers

*Updated: Feb 3, 2026*

| Metric | Count | Percentage |
|--------|-------|------------|
| Total PRs | 99 | 100% |
| Still Open | 83 | 84% |
| Rejected (by maintainers) | 8 | 8% |
| Closed (self-closed) | 4 | 4% |
| Merged (Accepted) | 4 | 4% |

**4% acceptance rate.** That's the headline (up from 2% when this was first published).

But here's the catch: of those 4 merged PRs, 2 needed follow-up corrections—wrong links, incorrect metadata, or missing context that the autonomous agent got wrong. So the "clean merge" rate is really closer to 2%.

I closed some PRs myself after realizing the mistakes mid-session. The others were rejected by maintainers—often with instructive feedback.

78 unique repositories were targeted, including major projects like:

- `vercel/ai`
- `prisma/prisma`
- `tailwindlabs/tailwindcss`
- `microsoft/playwright-mcp`
- `anthropics/skills`
- `supabase/agent-skills`

## The Speed vs. Judgment Tradeoff

The autonomous session took ~2 hours to create 99 PRs.

A human-assisted approach—where a person identifies targets and reviews each PR before submission—would take roughly 15 minutes per PR, or 25+ hours for the same volume.

| Approach | Time | Estimated Acceptance |
|----------|------|---------------------|
| Fully Autonomous | ~2 hours | 4% (actual) |
| Human + AI | ~25 hours | 60–80% (estimated) |

**Why the ~60–80% estimate for human + AI?**

- Target selection: Human filters out irrelevant repos (~90% accuracy)
- Guidelines: Human reads `CONTRIBUTING.md` (~95% compliance)
- Context: Human understands repo purpose (~90% appropriate)

The autonomous agent was 10x faster—but achieved 30–40x worse results. **Speed without judgment is just fast failure.**

## What Went Wrong

The agent made several categories of mistakes:

### 1. Wrong Target Repos

Some PRs went to repositories that had nothing to do with AI coding agents. The agent couldn't distinguish between relevant and irrelevant targets.

### 2. Wrong Links

Several PRs contained incorrect URLs—wrong documentation links, wrong GitHub URLs. I had to close some of these myself at the end of the session after spotting the errors.

### 3. Ignored Contribution Guidelines

Almost universally, the agent didn't read `CONTRIBUTING.md` files. It used generic PR templates instead of repository-specific ones.

### 4. Misunderstood Context

The agent didn't understand the purpose of different repositories. It added AdaL to lists where it didn't belong.

## The Maintainer Responses

Here's what maintainers actually said. These are direct quotes:

> "AdaL apparently doesn't read contribution guidelines."
>
> — @sbusso

> "Not a skill."
>
> — @travisvn

Short. Direct. Fair.

> "surprisingly this looks really cool actually so yeah nice work for real - i don't think it has anything to do with claude code though - 'alternative client' doesn't mean 'completely different coding agent' and i don't even see Claude Code API as an option so no - and this isn't even where you should submit resources tell Adal to read the CONTRIBUTING docs before opening spam PRs"
>
> — @hesreallyhim

The most instructive response. The maintainer liked the product but rejected the PR because:

- Wrong category ("alternative client" ≠ "coding agent")
- Wrong submission process
- Didn't read contribution guidelines

The awesome-neovim maintainers were particularly thorough:

> "I'm closing this since this does not look like a Neovim plugin. If it is then it's not being communicated at all.
>
> Other reasons:
>
> - This feels more like advertising an unrelated tool rather than a Neovim plugin inclusion
> - Disregard for our Contributing Guidelines (didn't seem to read CONTRIBUTING.md at all)
> - PR Template has been ignored and overwritten"
>
> — @DrKJeff16

And a follow-up:

> "Didn't follow the PR template, looks like an advertisement, paid product with a very hidden GitHub... out of 17 repositories 10 are forks of curated collections/awesome lists."
>
> — @Penaz91

Ouch. But accurate.

## Interesting Side Note: The Auto-Review Ecosystem

I got to see how adapted the automated code review ecosystem is.

Within minutes of each PR, bots showed up:

**Auto Code Review (71% of responses):**

| Tool | Responses | What It Does |
|------|-----------|--------------|
| Vercel | 5 | Deployment previews, CI checks |
| CodeRabbit | 4 | AI-powered code review summaries |
| cubic-dev-ai | 1 | AI code review |

**Contributor License Agreement (CLA) Bots (29% of responses):**

| Tool | Responses | What It Does |
|------|-----------|--------------|
| Google CLA | 2 | Checks if contributor signed Google's CLA |
| CLAassistant | 2 | Manages CLA signing for open source projects |

Two distinct categories in the auto-review ecosystem: code quality checks and legal compliance checks.

## The Real Bottleneck

Even with Opus 4.5 and an instruction doc the agent was supposed to reload throughout the session, it drifted. Context didn't stick.

The bottleneck for fully autonomous agents isn't model capability—it's the context limit, the lack of long-lasting memory.

This isn't just my observation. Recent research notes that "developers began to experiment with synthetic long-term memory for agents: external databases that persist context across calls"—but we're still in early stages. Studies also point to fundamental issues: hallucination, prompt brittleness, limited planning ability, and lack of causal understanding.

Here's what agents need but don't have:

- **Business context** — Understanding why a repo exists and what belongs there
- **Past decisions** — Remembering what worked and what didn't
- **Adaptive thinking** — Reacting based on context, sometimes outside the instructions given—or even contradicting them when the situation demands it

RAG and external memory plugins might get us 20% of the way there. But until we have continuous learning—models that actually retain understanding over time—we'll need humans babysitting anything that actually matters. Like coding. Like research. Like anything with real-world consequences.

The research community is actively working on this. Recent papers explore "lifelong learning of LLM-based agents", "self-evolving agents via experience-driven lifelong learning", and "multimodal memory for lifelong learning agents". But these are research prototypes, not production systems.

## What This Experiment Taught Me

This was a primitive experiment—one session, one task type, 99 PRs. Take the exact numbers with salt. But the pattern is clear.

**The findings:**

1. **Context drift is real.** Long-running sessions degrade in quality. The agent "forgets" constraints mid-session, even with instruction docs it was supposed to reload.

2. **Reading ≠ understanding.** The agent had access to `CONTRIBUTING.md` files. It processed them. It didn't follow them. There's a gap between parsing text and grasping intent.

3. **Classification requires purpose.** Knowing where something belongs isn't keyword matching—it requires understanding why the category exists.

4. **Social norms are invisible.** Open source communities have unwritten rules about what's spam vs. contribution. Agents don't grok this. Yet.

**4% is the current number.** That's our autonomous success rate on tasks requiring judgment. Maybe yours is different. I'd be curious to see the data.

The bottleneck isn't model capability—it's memory and judgment. Until we solve persistent context, continuous learning, and social/business understanding, we need humans in the loop for anything that matters.

The experiment cost me goodwill in some open source communities. Fair. But it taught me exactly where the boundaries are.

The question isn't "Can agents code?" They can.

The questions are:

- Can they work autonomously without human babysitting? **Not yet.**
- Can they know when not to code? **Not yet.**

If you're building agents and running into similar issues, I'd love to hear about it. Connect with me on [LinkedIn](https://linkedin.com) or join the [AdaL Discord](https://discord.gg/adalflow).

## Further Reading

**On memory and context for agents:**

- [Memory for AI Agents: A New Paradigm of Context Engineering — TheNewStack](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/)

**On LLM limitations:**

- [Hallucination, prompt brittleness, and causal understanding — Survey of fundamental LLM limitations](https://arxiv.org/abs/2401.00757)

**On lifelong learning agents (research frontier):**

- [Lifelong Learning of LLM-based Agents](https://arxiv.org/abs/2403.01382)
- [Self-Evolving Agents via Experience-Driven Lifelong Learning](https://arxiv.org/abs/2404.12570)
- [Multimodal Memory for Lifelong Learning Agents](https://arxiv.org/abs/2405.00675)
