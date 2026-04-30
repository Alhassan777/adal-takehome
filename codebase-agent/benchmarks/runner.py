"""Core runner: programmatic agent invocation for benchmark evaluation.

Wraps the engine factory and session management so each benchmark adapter
only needs to supply (repo_path, question, config) and gets back a result dict.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from codebase_agent.config import ExecutionMode
from codebase_agent.core.session import Session, SessionConfig, get_or_init_session
from codebase_agent.models import ParsedQuery
from codebase_agent.workflows.engine import create_engine

from .configs import AblationConfig


@dataclass
class RunResult:
    """Result of a single benchmark task run."""

    question: str
    answer: str
    config_id: str
    repo_path: str
    duration_s: float
    success: bool
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    raw_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "config_id": self.config_id,
            "repo_path": self.repo_path,
            "duration_s": self.duration_s,
            "success": self.success,
            "tool_calls": self.tool_calls,
            "error": self.error,
        }


def init_session_for_config(repo_path: str, config: AblationConfig) -> Session:
    """Initialize (or retrieve cached) session for a given repo + config."""
    session_cfg = SessionConfig(
        use_lsp=config.use_lsp,
        use_summaries=config.use_summaries,
        execution_mode=config.mode,
    )
    return get_or_init_session(repo_path, config=session_cfg)


def run_agent(
    repo_path: str,
    question: str,
    config: AblationConfig,
    *,
    session: Session | None = None,
) -> RunResult:
    """Run the agent on a single question and return structured results.

    Args:
        repo_path: Path to the target repository.
        question: The benchmark question to ask.
        config: Ablation configuration to use.
        session: Pre-initialized session (avoids re-init overhead for batches).
    """
    start = time.time()

    try:
        if session is None:
            session = init_session_for_config(repo_path, config)

        engine = create_engine(
            mode=config.mode,
            index=session.index,
            root_path=session.root_path,
            lsp=session.lsp,
        )

        parsed = ParsedQuery(raw_query=question, clean_query=question)
        result = engine.answer(parsed)

        duration = time.time() - start
        answer_text = result.get("answer", result.get("final_text", ""))
        tool_calls = result.get("tool_calls", [])

        return RunResult(
            question=question,
            answer=answer_text,
            config_id=config.name,
            repo_path=repo_path,
            duration_s=duration,
            success=True,
            tool_calls=tool_calls,
            raw_result=result,
        )

    except Exception as e:
        duration = time.time() - start
        return RunResult(
            question=question,
            answer="",
            config_id=config.name,
            repo_path=repo_path,
            duration_s=duration,
            success=False,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        )


def run_batch(
    repo_path: str,
    questions: list[str],
    config: AblationConfig,
    *,
    progress_callback=None,
) -> list[RunResult]:
    """Run a batch of questions on the same repo with the same config.

    Initializes the session once and reuses it across all questions.
    """
    session = init_session_for_config(repo_path, config)
    results = []

    for i, question in enumerate(questions):
        result = run_agent(repo_path, question, config, session=session)
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(questions), result)

    return results
