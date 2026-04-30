# Real-World Use Case: LinkedIn Recruitment Agent with AdalFlow

*November 21, 2025 · 3 min read · SylphAI*

**Tags:** AdalFlow, Agents, Automation

Hiring top talent is one of the most resource-intensive parts of building a company. Recruiters spend hours scrolling LinkedIn, opening profiles, copying notes, and crafting outreach messages.

What if we could automate that entire workflow—turning hours of manual searching into minutes of AI-assisted sourcing?

That's exactly what we built using AdalFlow's Agent + Runner architecture combined with browser automation via Chrome DevTools Protocol (CDP).

## Before vs After

**❌ BEFORE: 2–3 hours per role (Manual)**

- Navigate to LinkedIn people search
- Type in "Product Manager, San Francisco"
- Scroll endlessly, click into profiles
- Skim experience, education, skills
- Take notes in spreadsheets
- Write & send DMs manually

**✅ AFTER: 10 minutes per role (Agentic)**

- Run: `linkedin-agent --query "Product Manager" --limit 10`
- Agent plans and executes:
  - Extract profiles via browser automation
  - Evaluate candidates with scoring models
  - Draft personalized outreach messages

## Architecture

We structured the solution around a global state shared between tools. Each tool contributes partial data (search results, profiles, evaluations, outreach drafts), which the Agent combines into a full pipeline.

```
Agent → Planner + Tools (search, extract, evaluate, outreach)
Runner → Execution loop with error handling and logging
```

## The LinkedInAgent Implementation

```python
class LinkedInAgent:
    def __init__(self, model_client=None, model_kwargs=None, max_steps=None):
        model_client = model_client or OpenAIClient()
        model_kwargs = model_kwargs or {"model": "gpt-4o", "temperature": 0.3}
        max_steps = max_steps or 6

        self.tools = [
            SmartCandidateSearchTool,        # 1. Search LinkedIn via CDP
            ExtractCandidateProfilesTool,    # 2. Extract structured data
            CandidateEvaluationTool,         # 3. Score candidates
            CandidateOutreachGenerationTool, # 4. Draft outreach
            SaveOutreachResultsTool,         # 5. Persist results
        ]

        self.agent = Agent(
            name="LinkedInRecruiter",
            tools=self.tools,
            model_client=model_client,
            model_kwargs=model_kwargs,
            max_steps=max_steps,
        )
        self.runner = Runner(agent=self.agent, max_steps=max_steps)
```

## Sample Output

```json
[
  {
    "name": "Alex Chen",
    "title": "Senior Product Manager @ Stripe",
    "location": "San Francisco Bay Area",
    "profile_url": "https://linkedin.com/in/alexchen",
    "score": 0.92,
    "outreach_message": "Hi Alex, I came across your experience at Stripe…"
  },
  {
    "name": "Maria Lopez",
    "title": "PM, Growth @ Airbnb",
    "location": "San Francisco Bay Area",
    "score": 0.88,
    "outreach_message": "Hi Maria, your background in growth product design really stood out…"
  }
]
```

## Looking Forward

As the LLM landscape evolves, frameworks like AdalFlow will become the backbone of application development. Just as PyTorch accelerated deep learning, AdalFlow has the potential to democratize LLM app building—from chatbots to agents to beyond.

🚀 AdalFlow isn't just another library. It's a paradigm shift in how we think about programming with language models.

## References

- [AdalFlow GitHub](https://github.com/SylphAI-Inc/AdalFlow)
- [LinkedIn Agent GitHub](https://github.com/SylphAI-Inc/linkedin-agent)
- [AdalFlow Documentation](https://adalflow.sylph.ai)
- [LLM-AutoDiff Paper](https://arxiv.org/abs/2501.16673)
