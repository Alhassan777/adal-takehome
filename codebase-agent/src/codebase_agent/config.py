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

INDEX_DIR = ".cache"
INDEX_FILE = "codebase_index.msgpack"
HASH_FILE = "file_hashes.msgpack"
SUMMARY_FILE = "summaries.msgpack"
TRACE_DIR = "traces"
