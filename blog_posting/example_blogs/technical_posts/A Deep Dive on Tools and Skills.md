# A Deep Dive on Tools and Skills

*January 30, 2026 · 6 min read · AdaL CLI Team*

**Tags:** ai-agents, mcp, skills, engineering, tools

*From the AdaL CLI team, building a self-evolving coding agent*

People keep asking: "Should I use MCP or Skills?" It's the wrong question. They solve completely different problems.

MCP standardizes service access—how your agent authenticates and calls APIs. Skills package knowledge—how your agent learns to use those services well.

Let me explain with data and real examples.

## MCP: Standardizing Service Access

MCP (Model Context Protocol) does one thing well: standardized API access for AI agents.

Every service already has an API. GitHub has an API. Linear has an API. PostHog has an API. The problem isn't access—it's standardization.

Composio's analysis captures it: "APIs are powerful, but making them work for LLM agents takes heavy lifting—clear docs, schema handling, context management, and custom integrations."

MCP solves this by standardizing:

- **Discovery**: Agent asks "What tools do you have?" and gets a machine-readable list
- **Authentication**: OAuth flows handled by the MCP client
- **Schema**: Consistent JSON-RPC interface across all services
- **Error handling**: Semantic feedback the model can interpret

The result? GitHub MCP, Linear MCP, Sentry MCP—each maintained by the service provider, handling their own authentication.

### The Numbers

- 8M+ downloads (Nov 2024 → Apr 2025)
- 97M+ monthly SDK downloads
- 5,800+ servers, 10,000+ published
- Block built 60+ internal MCP servers

The Pragmatic Engineer surveyed 46 engineers. The pattern—MCP servers from service providers work great:

- **Playwright MCP**: "Browser automation via Playwright's accessibility tree" — Engineer at self-driving startup
- **Linear MCP**: "We paste in a link to an issue and ask Cursor to complete the ticket"
- **Sentry MCP**: "I'll give Cursor a Sentry issue link and ask it to troubleshoot"
- **Figma MCP**: "Excellent first draft of React Native UI code" — Staff Engineer at Infinite Red

### The Real Question: Why MCP When APIs Exist?

freeCodeCamp's analysis is direct: "AI models cannot safely call APIs on their own. They have no built-in execution environment, no way to store secrets, and no limits."

MCP provides the safety layer:

- Model never sees API keys or tokens
- MCP server handles the actual network call
- Returns only safe data to the model

But here's the limitation: MCP only handles service access. It doesn't teach your agent how to use those services effectively.

## Skills: Packaging Knowledge

Skills are completely different. They're not about service access—they're about expertise.

A Skill is a markdown file that teaches your agent:

- Best practices for using a tool
- Workflows for common tasks
- Context about your specific setup
- Scripts for deterministic operations

### Real Example: PostHog Skill

We have a PostHog Analytics Skill in our repo. It doesn't replace the PostHog API. It teaches the agent how to use the PostHog API effectively.

The Skill includes:

- How to set up API keys
- JSON config format for dashboards
- Script for create/sync/update/export operations
- Insight types and their parameters
- Environment variables and defaults

When an agent reads this Skill, it knows:

- How to structure a dashboard config
- What commands to run (`./scripts/posthog_sync.sh create config.json`)
- What the expected output looks like
- How to troubleshoot common issues

The Skill packages the expertise. The API provides the access.

### Browser Use Skill

Same pattern for browser automation. You might have:

- Playwright MCP for the actual browser access
- Browser Use Skill for best practices on automation

The Skill would teach:

- How to structure test flows
- When to use accessibility selectors vs CSS
- How to handle dynamic content
- Patterns for login flows

The MCP gives you the capability. The Skill gives you the knowledge.

## Why They're Orthogonal

| Aspect | MCP | Skills |
|--------|-----|--------|
| Purpose | Service access | Domain knowledge |
| Format | JSON-RPC servers | Markdown files + scripts |
| Maintained by | Service providers | Your team |
| Authentication | OAuth/tokens | None (just docs) |
| Requires | Running process | Just `git clone` |
| Updates | Server deployment | `git pull` |

MCP answers: "How do I authenticate and call this service?"
Skills answer: "How do I use this service effectively?"

## The Overlap Concern

You're right that MCP overlaps with APIs—both provide service access. MCP is essentially a standardized wrapper.

Medium's analysis: "MCP isn't replacing APIs—it's adding a layer on top, optimized for AI."

The value is standardization:

- **Before**: Each API has different auth, error handling, data formats
- **After**: "Once an AI knows how to use one MCP, it knows how to use any"

But Skills don't overlap with either. They're packaging knowledge, not access.

## Real-World Patterns

### Pattern 1: Service Access + Usage Knowledge

**PostHog integration:**

- Could use PostHog API directly (or future PostHog MCP)
- Plus PostHog Skill for dashboard best practices

**GitHub integration:**

- GitHub MCP for repos, PRs, issues
- Plus Skills for your team's PR workflow, code review checklist

### Pattern 2: Tool + Methodology

**Browser automation:**

- Playwright MCP or Chrome DevTools MCP
- Plus Skills for your test patterns, accessibility checks

**Error tracking:**

- Sentry MCP for issue access
- Plus Skills for your triage workflow, escalation procedures

### Pattern 3: Knowledge-Only (No MCP Needed)

Your codebase:

- Architecture decisions → Skill
- Deployment procedures → Skill
- Business logic → Skill

No MCP required—these are pure documentation for your agent.

## What We Built at AdaL

AdaL treats both as first-class:

**MCP Integration:**

- Native support for Playwright, Chrome DevTools, Linear
- Secure client with credential management
- Compatible with all standard MCP servers

**Skills System:**

- Compatible with Claude Code skills format
- Three sources: personal (`~/.adal/skills/`), project (`.adal/skills/`), plugins
- On-demand loading when relevant
- Optional bash scripts for deterministic operations

Real example from our repo:

- `posthog-analytics` Skill with sync scripts
- Agent learns PostHog patterns from the Skill
- Could combine with future PostHog MCP for direct API access

## The Takeaway

Stop asking "MCP or Skills?" They solve different problems:

**Use MCP when:**

- You need standardized service access
- The service provider maintains an MCP server
- You want automatic OAuth/authentication handling

**Use Skills when:**

- You're packaging knowledge about how to use a tool
- You have team-specific workflows and best practices
- You want documentation your agent can learn from
- No server process is acceptable (security, simplicity)

**Use both when:**

- You need service access (MCP) AND domain expertise (Skills)
- Example: Linear MCP for issue access + Skills for your team's development workflow

The best agents combine standardized tool access (MCP) with packaged expertise (Skills). That's what we're building at AdaL—and what we've seen work in production.

## References

- [API vs MCP: Everything You Need to Know — Composio](https://composio.dev/blog/api-vs-mcp)
- [MCP vs APIs: What's the Real Difference? — freeCodeCamp](https://www.freecodecamp.org/news/mcp-vs-apis)
- [Building MCP Servers in the Real World — The Pragmatic Engineer](https://newsletter.pragmaticengineer.com)
- [Complete Guide to MCP Enterprise Adoption — Market Data](https://marketdata.app)
- [AdaL Skills Documentation — SylphAI](https://adalflow.sylph.ai/docs/skills)
