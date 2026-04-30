AdaL CLI v0.9.1: Subagents, 2x Cost Efficiency, and Free GLM Models All March
New to AdaL? Learn what AdaL CLI is → · Read the docs →

A lot has happened since v0.8.0. AdaL CLI v0.9.1 is our biggest release yet — introducing subagents for intelligent task delegation, doubling cost efficiency through prompt caching, expanding to 15+ new models across five providers, and launching a free month of GLM models in partnership with Z.ai.

Here's everything that's new.

🤖 Subagents: Smarter Task Delegation
The headline feature of this release is subagents — lightweight agents that run on fast, cheap models to handle context-heavy tasks like codebase exploration, multi-file reads, and web research.

Instead of the main agent spending expensive tokens scanning through dozens of files, it now delegates discovery work to a subagent. The subagent gathers context, synthesizes findings, and returns a concise summary — so the main agent can focus on reasoning and implementation.

What this means for you:

Lower cost — context gathering runs on cheaper models
Faster responses — subagents specialize in retrieval, not generation
Better results — the main agent gets pre-digested context instead of raw file dumps
In v0.9.1, we further optimized subagent performance and error self-recovery, making the entire orchestration loop more reliable.

💰 2x Cost Efficiency with Prompt Caching
We've optimized prompt caching across the board, making AdaL 2x more cost-effective than before. Combined with subagents, improved memory management, and better context window utilization, your credits go significantly further — especially in long sessions.

Other efficiency improvements include:

Corrected OpenAI context windows from 400k to the actual 272k, preventing unnecessary compaction
Smoother long-session handling with improved memory compaction logic
Context percentage display in the footer so you always know where you stand
🆕 New Models Since v0.8.0
We've added 15+ new models across multiple providers. Here are the highlights:

Top New Models
Model	Provider	Highlight
GPT-5.4	OpenAI	Latest and most capable
GPT-5.3 Codex	OpenAI	New default model — optimized for code
GLM-5	Z.ai	Production-grade, free in March
GLM-4.7 FlashX	Z.ai	Fast and efficient
By Provider
OpenAI — GPT-5.4, GPT-5.3 Codex (now default), GPT-5.2 Codex, and deprecated older variants in favor of Codex-optimized models.

Z.ai — GLM-5, GLM-4.7 FlashX, and 3 additional models. Among the best for production-grade tasks.

Anthropic — Claude Sonnet 4.6 joined since v0.8.0.

Google — Gemini 3.1 Pro with improved agentic capabilities.

MiniMax — M2.5 and M2.5 Highspeed for fast, cost-effective workflows.

Ollama — Local model support (preview) for running models on your own hardware.

ChatGPT Subscription Support
Already paying for ChatGPT? You can now use your existing ChatGPT subscription directly in AdaL to access OpenAI models — no separate API key needed. Set it up in /model and start using GPT-5.4 and GPT-5.3 Codex through your subscription.

🎁 March Free Deal: All GLM Models, All Month
Coding agents can make the impossible possible for more people. But many are still left out due to affordability.

Thanks to our generous partner Z.ai, we are offering all GLM models to our users for free for the entire month of March.

This is our joint effort to support the global adoption of AI coding tools and to support women in tech.

GLM-5, GLM-4.7 FlashX, and three more models are included. They are among the best for production-grade tasks.

You can use AdaL CLI for free for one month.

Watch: Building a Doodle-to-Pixel-Art App with GLM
Watch how we built a doodle-to-pixel-art app — from design and MVP to a fully working product — entirely with AdaL and GLM models.


Hope you all enjoy it. 🎨

Image Generation & Editing
AdaL now includes built-in image generation and editing powered by Nano Banana 2.

The problem: Image generation and editing through AI requires surprisingly precise prompting. For generation, you need to specify style, lighting, composition, camera angles, and mood — a vague prompt produces vague results. For editing, it's even harder: you need to describe exactly what to change, what to preserve, and how to handle composition, aspect ratios, and resolution. One imprecise instruction and the model regenerates the entire image instead of editing it. Most tools leave all of this to the user.

How AdaL solves it: AdaL constructs precise, structured prompts behind the scenes. For generation, it translates your intent into detailed scene descriptions with the right style cues. For editing, it adds explicit preservation clauses, matches aspect ratios to the original, and manages the full prompt pipeline. You describe what you want. AdaL handles the prompting.

Here's a real example — changing just the car color while preserving every other detail:

Original red car
Original

Edited blue car
Edited — color changed to blue

Same car, same angle, same studio lighting — only the color changed. Generate illustrations, edit existing images, create diagrams, and more — all from within your coding workflow.

⚡ More Highlights
Headless mode — Run AdaL non-interactively with adal -q "query" for CI/CD and scripting
Redesigned /model panel — Provider-specific sections, pricing metadata, and recommended models
AdaL Web — Real-time git branch updates, sidebar diff viewer, and subagent parity with CLI
UI polish — Click-to-expand, inline diff highlighting, floating header, improved bash confirmations
Get Started
npm install -g @sylphai/adal-cli
adal
Update to v0.9.1 to access all the new models, subagents, and the free GLM offer.

New users get $5 in credits to get started!

Learn More
Full changelog →
Documentation →
Discord Community →
Share Your Feedback
Join the Discord Community to share your feedback and let us know how you're using the free GLM models!

On this page
🤖 Subagents: Smarter Task Delegation
💰 2x Cost Efficiency with Prompt Caching
🆕 New Models Since v0.8.0
🎁 March Free Deal: All GLM Models, All Month
Image Generation & Editing
⚡ More Highlights
Get Started
Learn More
Share Your Feedback
📬
Subscribe to the Source
Get engineering insights, agent patterns, and AdaL updates delivered directly to your inbox.

you@example.com
Subscribe →
Comments

sylphai-blog $ cd ..
More Posts
→
© 2026 SylphAI. All rights reserved.

