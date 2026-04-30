# The Ultimate Guide to Agentic Tool Calling: From Native Tool Calling to Best Custom Approach

## TL;DR

When you call an LLM API with tools and get back structured tool calls, you're seeing a translated abstraction. Every provider—Anthropic, OpenAI, Google, MiniMax—returns tool calls as JSON objects that their inference layer parsed from the model's raw text output. The model itself generates XML tags, special tokens, or custom delimiters. A parser extracts the structured data before it reaches you.

We ran benchmarks across 5 providers and captured real native tool call outputs. Here's what they actually look like—and why it matters for anyone building agent systems.

## What Native Tool Calls Actually Look Like

Every provider's "native tool calling" feature works the same way under the hood: the model generates text, and the provider's inference engine parses it into structured objects. Here's what each provider returns when you ask it to read a file:

### Anthropic Claude — `tool_use` Content Blocks

Claude returns tool calls as typed content blocks with `toolu_` prefixed IDs:

```json
[
  {
    "type": "text",
    "text": "I'll help you replace the docstring. Let me first read the file."
  },
  {
    "type": "tool_use",
    "name": "LocalFileOps_read_file",
    "input": {
      "file_path": "adalflow/core/generator.py"
    },
    "id": "toolu_01VTMiSzmQAuo1goF4bkvudZ"
  }
]
```

Notice Claude often includes a text block before the tool call—the model naturally wants to explain what it's doing. The API packages both into a single response. This is a real output from our benchmark.

### OpenAI GPT-5.2-Codex — `call_` Prefixed IDs

OpenAI's native format looks similar but uses `call_` prefixed IDs and slightly different field structure:

```json
[
  {
    "name": "LocalFileOps_read_file",
    "input": {
      "file_path": "adalflow/core/generator.py",
      "start_line": 1,
      "end_line": 400,
      "include_line_numbers": true
    },
    "id": "call_LBEck2LfMMn7HZePnEbGwDWP"
  }
]
```

GPT models tend to be more verbose with parameters—filling in optional arguments that other models skip. The model generated this as text internally; OpenAI's inference layer parsed and validated it.

### Google Gemini — Function Name as ID

Gemini's native tool calls use the function name itself as the ID pattern:

```json
[
  {
    "name": "LocalFileOps_read_file",
    "input": {
      "file_path": "adalflow/core/generator.py"
    },
    "id": "call_LocalFileOps_read_file"
  }
]
```

The `call_LocalFileOps_read_file` ID reveals something: Gemini's inference engine is generating IDs deterministically from the function name, unlike Anthropic and OpenAI which use random hashes. This suggests different levels of server-side processing.

### MiniMax M2.5 — `call_function_` with Random Suffix

MiniMax returns tool calls with `call_function_` prefixed IDs:

```json
[
  {
    "name": "LocalFileOps_read_file",
    "input": {
      "file_path": "adalflow/core/generator.py"
    },
    "id": "call_function_lctl7m2smufa_1"
  }
]
```

But here's the reveal: MiniMax is fully transparent about what the model actually generates before this JSON is constructed. The raw model output is XML:

```xml
<minimax:tool_call>
  <invoke name="LocalFileOps_read_file">
    <parameter name="file_path">adalflow/core/generator.py</parameter>
  </invoke>
</minimax:tool_call>
```

The inference engine (vLLM/SGLang) regex-parses this XML and converts it to the JSON you see above. This is the translation layer in action.

## The Parser Behind the Curtain

MiniMax publishes their actual parsing code—a rare look at what every provider does internally:

```python
import re
import json

def parse_tool_calls(model_output, tools=None):
    """Extract tool calls from MiniMax model's raw XML output."""
    if "<minimax:tool_call>" not in model_output:
        return []

    tool_calls = []
    # Match all <minimax:tool_call> blocks
    tool_call_regex = re.compile(
        r"<minimax:tool_call>(.*?)</minimax:tool_call>", re.DOTALL
    )
    invoke_regex = re.compile(
        r"<invoke name=(.*?)</invoke>", re.DOTALL
    )
    parameter_regex = re.compile(
        r"<parameter name=(.*?)</parameter>", re.DOTALL
    )

    for block in tool_call_regex.findall(model_output):
        for invoke in invoke_regex.findall(block):
            name = extract_name(invoke.split(">")[0])
            params = {}
            for match in parameter_regex.findall(invoke):
                param_name = extract_name(match.split(">")[0])
                param_value = match.split(">", 1)[1].strip()
                params[param_name] = convert_type(param_value, tools)
            tool_calls.append({"name": name, "arguments": params})

    return tool_calls
```

This is regex-based XML extraction → JSON conversion. Every provider does a version of this—MiniMax just shows their work.

## The Internal Formats: A Provider-by-Provider Breakdown

Now that we've seen the output, let's look deeper at what each model actually generates and how the conversation is structured internally.

### MiniMax M2.5: Full XML with Custom Control Tokens

MiniMax is the most transparent. Their tool calling guide shows the complete internal format:

```
]~!b[]~b]system
You are a helpful assistant.

# Tools

<tools>
<tool>{"name": "search_web", "description": "...", "parameters": {...}}</tool>
</tools>

When making tool calls, use XML format:
<minimax:tool_call>
  <invoke name="tool-name">
    <parameter name="param">value</parameter>
  </invoke>
</minimax:tool_call>
[e~[
]~b]user
What's the weather?[e~[
]~b]ai
<think>I should call the weather tool...</think>
<minimax:tool_call>
  <invoke name="get_weather">
    <parameter name="location">San Francisco</parameter>
  </invoke>
</minimax:tool_call>
```

The control tokens (`]~!b[`, `[e~[`, `]~b]`) are the model's internal role markers—completely hidden from API users.

### Hermes (NousResearch): ChatML + XML-Wrapped JSON

Hermes models use ChatML tokens and `<tool_call>` tags:

```
<|im_start|>assistant
<scratch_pad>
The user wants weather info. I should use get_weather.
</scratch_pad>
<tool_call>
{"name": "get_weather", "arguments": {"location": "SF"}}
</tool_call>
<|im_end|>
```

The `<scratch_pad>` is internal reasoning that gets stripped. The JSON inside `<tool_call>` tags is extracted by the inference engine. Tags like `<tool_call>` are registered as special tokens in the tokenizer—they can't be accidentally split into subword fragments.

### Mistral: Bracketed Token Tags

Mistral uses `[TOOL_CALLS]` as a special token:

```
[TOOL_CALLS][{"name": "search", "arguments": {"query": "test"}}]
```

The inference engine watches the token stream for `[TOOL_CALLS]` and extracts the JSON that follows. Simple, effective—a hybrid approach with JSON content but a special token delimiter.

### Llama 3.x: JSON or Python Syntax

Meta's Llama models support multiple formats by version:

- **Llama 3.1**: JSON-based
- **Llama 3.2**: Pythonic format—the model outputs Python function calls:

```python
[get_weather(location="San Francisco", unit="celsius")]
```

vLLM maintains separate parsers for each because the "best" format depends on what the model was trained on.

### Anthropic Claude: Hidden System Prompt + Content Blocks

Anthropic is semi-transparent. Key architectural details from their docs and engineering blog:

**Hidden system prompt injection**: When you pass tools, Anthropic silently prepends a system prompt that teaches the model tool calling. AWS Bedrock confirms: "When you use tools, the Anthropic models automatically include a special system prompt that enables tool use."

**XML is Claude's native language**: Claude was trained on XML-structured content. Internal systems use `<available_skills>`, `<command-message>` tags throughout Claude's architecture.

**Content block architecture**: Claude integrates tools into standard messages as typed blocks:

```json
// Assistant generates tool_use blocks
{"role": "assistant", "content": [
  {"type": "text", "text": "Let me check the weather."},
  {"type": "tool_use", "id": "toolu_01A09q90qw",
   "name": "get_weather", "input": {"location": "SF"}}
]}

// Results come back as tool_result in user messages
{"role": "user", "content": [
  {"type": "tool_result", "tool_use_id": "toolu_01A09q90qw",
   "content": "72°F, sunny"}
]}
```

**Programmatic Tool Calling**: Claude's advanced mode generates Python orchestration code to call tools with loops and conditionals—the API translates tool definitions into Python function signatures.

### OpenAI: The Black Box

OpenAI is least transparent, but we know:

- Functions injected into system message—they count against context tokens
- GPT-OSS uses "Harmony" format with TypeScript-like `namespace functions { }` syntax
- Structured Outputs use constrained decoding—an FSA restricts token generation to enforce JSON schema compliance

## The Translation Layer

vLLM documents this clearly—every model needs its own parser:

| Model | What the Model Generates | How It's Parsed |
|-------|--------------------------|-----------------|
| MiniMax M2.5 | `<minimax:tool_call>` XML | Regex XML extraction |
| Anthropic Claude | XML-structured text | API layer → `tool_use` blocks |
| Hermes 2/3 | `<tool_call>` JSON-in-XML | Tag extraction |
| Mistral | `[TOOL_CALLS]` bracketed | Special token watching |
| Llama 3.2 | Pythonic `[func()]` | Python-like parser |
| Llama 3.1 | JSON with markers | Standard JSON parser |

All get converted to the exact same OpenAI-compatible format. vLLM even supports custom parser plugins—because every model family invents its own format.

## How Models Are Trained for Tool Calling

The training pipeline has evolved significantly. From *Simplicity is SOTA*:

1. **Pre-training on code**: Models develop structured output ability from code-heavy corpuses
2. **Self-supervised tool data**: ToolFormer-style approaches use LLMs to generate training queries, filter by whether tool calls improve predictions, then fine-tune
3. **Special token registration**: Tags like `<tool_call>` are registered as indivisible tokens—preventing subword fragmentation
4. **Think-before-act training**: Datasets include reasoning traces before tool calls, reducing hallucinations
5. **Negative examples**: "No-call" scenarios teach models when NOT to use tools

## Constrained Decoding: The Nuclear Option

Some providers add constrained decoding—using a Finite State Automaton to restrict which tokens can be generated. Lepton AI documents this:

> "By building the FSA based on a provided JSON schema, the inference engine performs rejection sampling to ensure that only 'legit' tokens are produced."

This guarantees valid JSON in a single pass. But it's optional—MiniMax, Hermes, and Mistral achieve reliable tool calling through training and format tags alone.

OpenAI's Structured Outputs uses constrained decoding; their standard function calling relies on training.

## Why This Matters

### JSON Isn't the Natural Format

LLMs are autoregressive text generators. They're better at producing structured text with clear delimiters (XML tags, special tokens) than syntactically valid JSON with proper escaping and bracket matching. Every major provider wraps tool calls in delimiters—because raw JSON extraction from free-form text is unreliable.

### The "Best" Format Is Model-Dependent

MiniMax chose XML. Llama 3.2 prefers Python syntax. Hermes wraps JSON in XML tags. There's no universal best format—it depends on what the model was trained on.

### You Can Build Your Own Format

If you're building agent systems, you don't need provider-native tool calls. There are two practical alternatives:

**Option 1: Custom tagged format.** Define your own delimited format (XML tags, special markers) with a dedicated parser. This gives you full control over prompt structure and output format. Systems like AdaL use tagged formats like `<TOOL_CALLS>` with custom parsers. In our benchmarks across 5 providers, this approach achieved 100% parse success rates while saving 32% on output tokens compared to native tool calls. The tradeoff: you need a robust parser and careful prompt engineering.

**Option 2: Strict JSON with constrained decoding.** Most major API providers now offer structured outputs—a mode where the inference engine constrains the model's token generation to only produce valid JSON matching a given schema. OpenAI calls this Structured Outputs, and open-source engines like vLLM and SGLang implement it as guided decoding—applying grammar-based token masks at each generation step to guarantee syntactically valid output. This gives you near-100% parse success rates while letting you control your own prompts and JSON schemas, without needing native tool call support.

### Provider APIs Hide Complexity

When you use tools in an API, you're benefiting from years of format experimentation, parser engineering, and constrained decoding infrastructure. Self-hosting with vLLM or SGLang requires configuring the right parser for your model—the translation layer doesn't come free.

## Summary

| What Users See | What Models Generate | Who Translates |
|----------------|---------------------|----------------|
| JSON `tool_calls` array | XML, special tokens, Python, custom formats | Inference engine (vLLM, SGLang, proprietary) |
| Clean function arguments | Raw text with delimiters | Model-specific parsers |
| Standardized API response | Provider-specific internal format | API layer |

The JSON tool call format is a user-facing abstraction, not a model-native capability. Behind every clean API response is a model generating tagged text and a parser converting it to JSON.
