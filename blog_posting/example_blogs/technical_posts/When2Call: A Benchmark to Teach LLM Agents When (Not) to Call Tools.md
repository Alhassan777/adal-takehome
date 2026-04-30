# When2Call: A Benchmark to Teach LLM Agents When (Not) to Call Tools

*September 25, 2025 · 3 min read · SylphAI*

**Tags:** LLM, Agents, Benchmarks

Large Language Models are no longer just text generators—they are becoming tool-augmented agents. They can fetch real-time data, query APIs, run code, or even control external systems.

But there's a subtle challenge:

> **When should a model call a tool, and when should it not?**

This is the focus of the new benchmark **When2Call**, which evaluates not just whether a model can call tools correctly, but also whether it can decide *if* it should call them in the first place.

Most benchmarks today assume tools are always available and useful. But in real-world scenarios:

- Sometimes parameters are missing → the model should ask a follow-up question.
- Sometimes tools don't exist → the model should refuse politely.
- Sometimes the answer is already obvious → no tool call needed.
- Sometimes the model hallucinates tools or parameters → leading to misleading outputs.

Bad tool-calling decisions lead to wasted computation, higher costs, or worse—hallucinated answers that users may trust.

## The When2Call Benchmark

When2Call introduces a benchmark + dataset + training regime to evaluate this decision-making step.

It defines four possible model behaviors:

1. **Tool Call** — use an available tool with correct parameters.
2. **Follow-Up Question** — ask for clarification if inputs are missing.
3. **Direct Answer** — respond directly if possible (but risky if tools are needed).
4. **Unable to Answer** — explicitly say tools are insufficient.

## Key Findings

- **Models often get it wrong.** Even GPT-4–level models sometimes hallucinate tools or parameters, or answer directly when they shouldn't.
- **Current datasets are biased.** Most training data only shows positive tool calls, so models lack exposure to "don't call" scenarios.
- **Adding When2Call helps.** Fine-tuning on this benchmark improves judgment, especially around follow-ups and refusals.
- **But trade-offs exist.** Some models become too conservative—refusing to call tools even when they should.
- **Preference optimization (RPO) balances the trade-offs better** than supervised fine-tuning (SFT).

## Practical Takeaways

If you're building LLM applications with tool use:

- **Train with negative examples** (missing info, unavailable tools).
- **Monitor tool hallucination** just like content hallucination.
- **Use both MCQ evaluation** (structured) and LLM-as-judge (free-form) to test decisions.
- **Consider preference optimization** for more balanced behavior.

## Conclusion

When2Call is a step toward making LLMs smarter, safer, and more honest in tool use.

It's not enough for models to know *how* to call a tool—they also need to know *when not* to call one.

That decision-making ability is what will separate today's chatbots from tomorrow's reliable AI agents.

## References

- [A dataset for training and evaluating LLMs on decision making about "when (not) to call" functions — NVIDIA/When2Call](https://github.com/NVIDIA/When2Call)
- [When2Call Dataset on HuggingFace](https://huggingface.co/datasets/nvidia/When2Call)
- [When2Call Paper on arXiv](https://arxiv.org/abs/2405.00675)
