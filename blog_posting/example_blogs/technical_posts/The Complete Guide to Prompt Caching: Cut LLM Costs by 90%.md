# The Complete Guide to Prompt Caching: Cut LLM Costs by 90%

*December 20, 2025 · 3 min read · SylphAI*

**Tags:** LLM, Optimization, Cost Reduction

## What You'll Learn

- Why LLMs recompute the same tokens repeatedly (and waste money)
- The mathematical foundation: KV cache and attention mechanism
- How to structure prompts for maximum cache hit rates
- Provider-specific strategies (Anthropic, OpenAI)
- Real-world cost savings and performance benchmarks

## The Problem

If you're building with LLMs, you've likely noticed a pattern: your application sends similar context repeatedly across requests.

**Example: Coding assistant**

```
Request 1:
  System prompt: "You are an expert Python developer..." (2000 tokens)
  User query: "Write a function to parse JSON" (10 tokens)

Request 2:
  System prompt: "You are an expert Python developer..." (same 2000 tokens!)
  User query: "Write a function to validate email" (10 tokens)
```

Without caching, you're paying full price for those 2000 system prompt tokens on every single request.

**With prompt caching:**

- First request: Pay full price (cache write)
- Subsequent requests: Pay 10% of price (cache read)
- **Result: 90% cost reduction + 75% faster responses**

## The Golden Rule: Static First, Dynamic Last

The key to effective prompt caching is putting static content at the beginning and dynamic content at the end.

**✅ Optimal Structure (maximizes cache hits):**

```
┌────────────────────────────────────────┐
│  Static system prompt  (5000 tokens)  │  ← Forms cacheable prefix
│  Tool definitions      (3000 tokens)  │  ← Extends cacheable prefix
│  Project context       (2000 tokens)  │  ← Still cacheable
│  Conversation history  (1000 tokens)  │  ← Partially cacheable
│  Current user query     (100 tokens)  │  ← Dynamic, not cached
└────────────────────────────────────────┘
Total cacheable: 10,000+ tokens
```

**❌ Bad Structure (breaks caching):**

```
┌────────────────────────────────────────┐
│  Current query         (100 tokens)   │  ← Dynamic first!
│  System prompt        (5000 tokens)   │  ← Can't cache (no prefix match)
└────────────────────────────────────────┘
Total cacheable: 0 tokens
```

## Provider Comparison

**Anthropic:**

- Explicit control via API
- ~100% cache hit rate when you ask for it
- Costs 25% more to cache, but saves 90% on cache hits
- Cache lasts 5–10 minutes

**OpenAI:**

- Automatic (you don't control it)
- ~50% cache hit rate
- Free (built into pricing)

## Real-World Example

**Coding Assistant: 10,000 requests/day**

- Static system prompt: 8,000 tokens
- Average user query: 200 tokens
- Cache hit rate: 90%

**Without caching:**

- Total: 10,000 × 8,200 = 82M tokens/day
- Cost (Anthropic): 82M × $3/M = **$246/day**

**With caching:**

- Cache writes: 1,000 × 8,000 @ $3.75/M = $30
- Cache reads: 9,000 × 8,000 @ $0.30/M = $21.60
- Uncached: 10,000 × 200 @ $3/M = $6
- **Total: $57.60/day**

**Savings: 76% cost reduction + 40–50% faster responses**

## Best Practices

**Build prompts from static to dynamic:**

```python
def build_prompt(system, tools, history, query):
    """Order matters: Static → Dynamic"""
    return "\n\n".join([
        system,               # Layer 1: Static (always cached)
        format_tools(tools),  # Layer 2: Semi-static
        format_history(history),  # Layer 3: Grows over time
        query                 # Layer 4: Always unique
    ])
```

- **Check minimum size**: Most providers require at least 1024 tokens for caching
- **Monitor performance**: Track hit rates and savings in your metrics

## Summary

| What | Detail |
|------|--------|
| What's cached | K and V matrices (intermediate calculations in attention) |
| Why it works | Linearity of matrix multiplication allows decomposition |
| Performance gain | 75% faster, 90% cheaper for cached tokens |
| Practical impact | Makes long conversations and repeated prompts much more efficient |

## References

- [ngrok.com blog post on prompt caching](https://ngrok.com/blog-post/prompt-caching)
- [How Prompt Caching Works](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
