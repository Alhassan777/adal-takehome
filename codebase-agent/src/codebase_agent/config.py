"""Configuration constants for the codebase agent."""

import os
from enum import Enum


class ExecutionMode(str, Enum):
    """Agent execution strategy."""

    ADAPTIVE = "adaptive"
    RLM = "rlm"


class SandboxMode(str, Enum):
    """REPL sandbox isolation level for RLM mode."""

    LOCAL = "local"
    DOCKER = "docker"


DEFAULT_EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "adaptive"))
DEFAULT_SANDBOX_MODE = SandboxMode(os.environ.get("RLM_SANDBOX", "local"))

OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_SUB_MODEL: str = os.environ.get("OPENAI_SUB_MODEL", "gpt-4o-mini")

SUMMARY_LLM_MODEL: str = os.environ.get("SUMMARY_LLM_MODEL", "gpt-4o-mini")
SUMMARY_BATCH_SIZE: int = int(os.environ.get("SUMMARY_BATCH_SIZE", "5"))

MAX_ADAPTIVE_ROUNDS: int = 15
MAX_RLM_ITERATIONS: int = 10
MAX_SUB_MODEL_DEPTH: int = 2
MAX_LEARNED_TOOLS: int = 20

# Per-token pricing as of April 2026: (input_cost_per_token, output_cost_per_token)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI -- flagship
    "gpt-5.5": (5.00 / 1_000_000, 30.00 / 1_000_000),
    "gpt-5.4": (2.50 / 1_000_000, 15.00 / 1_000_000),
    "gpt-5.4-mini": (0.75 / 1_000_000, 4.50 / 1_000_000),
    "gpt-5-mini": (0.25 / 1_000_000, 2.00 / 1_000_000),
    # OpenAI -- GPT-4.1 family
    "gpt-4.1": (2.00 / 1_000_000, 8.00 / 1_000_000),
    "gpt-4.1-mini": (0.40 / 1_000_000, 1.60 / 1_000_000),
    "gpt-4.1-nano": (0.10 / 1_000_000, 0.40 / 1_000_000),
    # OpenAI -- GPT-4o family
    "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    # OpenAI -- reasoning models
    "o3": (2.00 / 1_000_000, 8.00 / 1_000_000),
    "o3-mini": (1.10 / 1_000_000, 4.40 / 1_000_000),
    "o4-mini": (1.10 / 1_000_000, 4.40 / 1_000_000),
    # OpenAI -- legacy
    "gpt-4-turbo": (10.00 / 1_000_000, 30.00 / 1_000_000),
    "gpt-3.5-turbo": (0.50 / 1_000_000, 1.50 / 1_000_000),
    "o1": (15.00 / 1_000_000, 60.00 / 1_000_000),
    "o1-mini": (3.00 / 1_000_000, 12.00 / 1_000_000),
    # Anthropic -- current
    "claude-opus-4.7": (5.00 / 1_000_000, 25.00 / 1_000_000),
    "claude-opus-4.6": (5.00 / 1_000_000, 25.00 / 1_000_000),
    "claude-sonnet-4.6": (3.00 / 1_000_000, 15.00 / 1_000_000),
    "claude-haiku-4.5": (1.00 / 1_000_000, 5.00 / 1_000_000),
    # Anthropic -- legacy
    "claude-opus": (15.00 / 1_000_000, 75.00 / 1_000_000),
    "claude-sonnet": (3.00 / 1_000_000, 15.00 / 1_000_000),
    "claude-3.5-sonnet": (3.00 / 1_000_000, 15.00 / 1_000_000),
    "claude-haiku": (0.80 / 1_000_000, 4.00 / 1_000_000),
    "claude-haiku-3.5": (0.80 / 1_000_000, 4.00 / 1_000_000),
}

TOKEN_LIMITS: dict[str, int] = {
    # OpenAI
    "gpt-5.5": 128_000,
    "gpt-5.4": 128_000,
    "gpt-5.4-mini": 128_000,
    "gpt-5-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1-nano": 1_047_576,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o4-mini": 200_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    # Anthropic
    "claude-opus-4.7": 1_000_000,
    "claude-opus-4.6": 1_000_000,
    "claude-sonnet-4.6": 1_000_000,
    "claude-haiku-4.5": 200_000,
    "claude-opus": 200_000,
    "claude-sonnet": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-haiku": 200_000,
    "claude-haiku-3.5": 200_000,
}


DEFAULT_IGNORE_DIRS: set[str] = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "*.egg-info",
    ".cache",
}

SUPPORTED_EXTENSIONS: set[str] = {
    ".py",
    ".pyi",
}

MCP_SERVERS: list[dict[str, str]] = []
_mcp_raw = os.environ.get("MCP_SERVERS", "")
if _mcp_raw:
    for entry in _mcp_raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            transport, url = entry.split(":", 1)
            MCP_SERVERS.append({"transport": transport, "url": url})

INDEX_DIR = ".cache"
INDEX_FILE = "codebase_index.msgpack"
HASH_FILE = "file_hashes.msgpack"
SUMMARY_FILE = "summaries.msgpack"
TRACE_DIR = "traces"
