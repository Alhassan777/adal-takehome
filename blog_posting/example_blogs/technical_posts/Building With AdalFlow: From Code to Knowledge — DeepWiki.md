# Building With AdalFlow: From Code to Knowledge — DeepWiki

*November 26, 2025 · 3 min read · SylphAI*

**Tags:** AdalFlow, Documentation, DeepWiki

Today's article introduces one of the standout products built on AdalFlow: DeepWiki, an AI-powered documentation generator. It automatically transforms GitHub, GitLab, and BitBucket repositories into complete, interactive wikis—analyzing code structure, generating clean documentation, creating diagrams, and even enabling developers to "chat" with their repos.

## The Documentation Problem

Documentation is the bridge between code and understanding, yet countless open-source and internal projects still struggle with docs that are incomplete, outdated, or missing altogether. Writing good documentation requires deep knowledge, time, and constant maintenance—something most developers simply don't have.

DeepWiki is built on a simple insight: the code itself is the ultimate source of truth. If AI can read the entire repository, understand its structure, and generate the documentation automatically, we can dramatically improve engineering efficiency.

## Key Features

- **Instant Documentation**: Turn any GitHub, GitLab or BitBucket repo into a wiki in seconds
- **Private Repository Support**: Securely access private repositories with personal access tokens
- **Smart Analysis**: AI-powered understanding of code structure and relationships
- **Beautiful Diagrams**: Automatic Mermaid diagrams to visualize architecture and data flow
- **Easy Navigation**: Simple, intuitive interface to explore the wiki
- **Ask Feature**: Chat with your repository using RAG-powered AI
- **DeepResearch**: Multi-turn research process that thoroughly investigates complex topics
- **Multiple Model Providers**: Support for Google Gemini, OpenAI, OpenRouter, and local Ollama models

## Why AdalFlow?

DeepWiki needs far more than a simple LLM call. It must read entire repositories, split them into meaningful chunks, embed those chunks using different providers, index everything for fast retrieval, and then generate structured, reliable documentation at scale.

AdalFlow removes all of that complexity.

Just as PyTorch changed deep learning by offering a clean, intuitive, modular framework, AdalFlow brings that same philosophy to LLM workflows. With AdalFlow, every part of the workflow—from data preprocessing to embedding, retrieval, and generation—becomes a composable, inspectable, optimizable pipeline.

## The Sequential Pipeline

AdalFlow's `Sequential` component lets us describe a complete data pipeline the same way you'd write a PyTorch model:

```python
data_transformer = adal.Sequential(splitter, embedder_transformer)
db = LocalDB()
db.register_transformer(data_transformer, "split_and_embed")
db.load(documents)
db.transform("split_and_embed")
db.save_state(db_path)
```

- No scattered scripts
- No custom orchestration
- No brittle connections between steps

## Provider Flexibility

AdalFlow exposes a single interface across OpenAI, Google Gemini, Azure OpenAI, AWS Bedrock, DashScope, OpenRouter, and local Ollama. Switching providers is as simple as:

```python
client = GoogleGenAIClient()  # or OllamaClient(), OpenAIClient(), etc.
```

No refactoring. No conditional logic. No provider-specific errors leaking into application code.

## References

- [DeepWiki GitHub](https://github.com/AsyncFuncAI/deepwiki-open)
- [AdalFlow GitHub](https://github.com/SylphAI-Inc/AdalFlow)
- [AdalFlow Documentation](https://adalflow.sylph.ai)
