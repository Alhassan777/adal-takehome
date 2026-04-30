# Your Agent Can Babysit Your Training Run Now: AdaL Cron vs. Claude Code Scheduling

_April 16, 2026 · 4 min read · SylphAI_

**Tags:** adal-cron, agent-scheduling, session-automation, ml-monitoring, autonomous-agents

It's 11pm. You've kicked off a training run that'll take six hours. You want to sleep. But the last three times you did this, you woke up to either a NaN loss explosion at epoch 2 or a CUDA OOM at epoch 14 — and eight hours of compute wasted either way. So you stayed up. Again.

What if your agent could just watch it?

AdaL's new `/cron` command gives your live session a heartbeat — a repeating, self-directed check-in that runs through the same pipeline as everything else you type. Not a daemon. Not cloud infra. A session-scoped supervisor that fires every 10 seconds if you want it to, checks a file, takes action, and reports back.

---

## Why Most Agent Scheduling Gets This Wrong

The gap in agent scheduling isn't technical — it's conceptual. Cloud-level automation (GitHub Actions, cron daemons, Anthropic Cloud Routines) is built for durability and breadth: survive reboots, span repos, trigger on events. That's the right tool for nightly batch jobs.

But you're not building a nightly batch job right now. You're in a session. You have context loaded. You're watching a loss curve. You need a check every 30 seconds, not every hour. Hourly scheduling is too coarse to catch a NaN before the model checkpoint is already corrupt. And spinning up cloud infra for a six-hour babysitting session you own entirely is the wrong abstraction.

---

## AdaL Cron: A Repeating Prompt, Not a Daemon

The command is exactly what you'd hope:

```bash
/cron add 30s "read @logs/train.log, check for NaN loss or CUDA errors, if found run @scripts/recover.sh and notify me"
```

That fires once immediately, then every 30 seconds. Intervals can be as tight as `10s` or as long as `24h`. The minimum matters — 10 seconds is the difference between catching a NaN at step 50 vs. step 400.

What makes this more than a timer is **pipeline reuse**. The prompt executes through the same input pipeline as everything you type manually — `@file` references re-read the file fresh on every run, tool use is available, multi-step reasoning is live. When you write `@logs/train.log`, the agent isn't reading a snapshot from session start. It reads the current file on every tick.

The **queue-and-skip backpressure model** is simple and predictable: if AdaL is busy when the timer fires, one run is queued. Additional triggers while it's still busy are counted as skipped, not accumulated. No flood, no catch-up semantics. You can reason about it without doing math.

Opening `/cron` shows you the interactive status dialog — run count, skip count, countdown to next fire, interval presets. One cron per session. Setting a new one replaces the old one. Clears on exit.

That last point is intentional. This isn't infrastructure. It's supervision.

### What a Real Training Supervision Prompt Looks Like

```bash
/cron add 1m "@logs/wandb_run.log — check: (1) is val_loss decreasing? (2) any NaN or inf values? (3) GPU util below 50% for 3+ consecutive steps? If any condition true, describe the issue and run @scripts/triage.sh"
```

Every minute, your agent reads the live log, evaluates three conditions, and takes action if warranted. You go to sleep. The agent doesn't.

---

## Head-to-Head Comparison with Claude Code

Claude Code offers three scheduling primitives: `/loop` for session-tied automation in the CLI, Desktop Scheduled Tasks for local machine automation, and Cloud Routines for durable account-level jobs. Each targets a different layer of the automation stack — which is also why picking the right one requires understanding all three. The table below focuses on the dimensions that actually matter for the use case we're talking about: keeping an eye on a live job while you're working.

| Dimension    | AdaL Cron                                 | Claude `/loop`                | Claude Desktop Tasks             | Claude Cloud Routines      |
| ------------ | ----------------------------------------- | ----------------------------- | -------------------------------- | -------------------------- |
| Min interval | **10 seconds**                            | 1 minute (rounded + jitter)   | 1 hour                           | 1 hour                     |
| Persistence  | Session lifetime                          | 7 days + session lifetime     | Persists in app config           | Account-level, durable     |
| Execution    | Live session pipeline                     | Live session pipeline         | Local machine (app must be open) | Anthropic-managed cloud    |
| Triggers     | Time only                                 | Time + dynamic + reminders    | Time-based cadences              | Schedule, HTTP API, GitHub |
| Tasks        | 1 (replace-on-set)                        | Up to 50                      | Multiple                         | Account-level              |
| Best for     | Session supervision, tight feedback loops | Session babysitting (CI, PRs) | Persistent local automation      | Durable infra automation   |

---

## Where to Use Which

Today, Claude's Cloud Routines cover use cases that AdaL Cron doesn't "yet", durable automation that survives machine restarts, GitHub event triggers, multi-repo workflows. AdaL Cron is a v1: the feature is actively evolving, and persistence, broader trigger support, and cross-session scheduling are natural directions from here.

What AdaL Cron is already built for: the **session-native supervision loop** where you're present, context is loaded, and you need the agent checking every few seconds — not every hour. Here are 3 reasons it wins that domain:

1. **10x lower minimum latency** — 10s vs. 60s vs. 3600s. For a training loss curve, that's the difference between catching a divergence at step 50 and catching it at step 3000.
2. **No configuration overhead** — one session, one cron, one command. No picking the right primitive, no setting up cloud infra, no deciding whether to use `/loop` or routines based on how long the job runs.
3. **Always reading the latest state** — `@file` references in your cron prompt aren't snapshots. Every time the cron fires, AdaL re-reads the file from disk. So if your training log has grown by 200 lines since the last check, the agent sees those 200 lines — not a stale copy from when you first set the cron up.

---

## References

- [AdaL Cron documentation](https://adalflow.sylph.ai/docs/cron)
- [Claude `/loop` — Anthropic docs](https://docs.anthropic.com/en/docs/claude-code/cli-reference)
- [Claude Scheduled Tasks — Desktop](https://support.anthropic.com/en/articles/scheduled-tasks)
- [Claude Cloud Routines](https://docs.anthropic.com/en/docs/claude-code/cloud-routines)
