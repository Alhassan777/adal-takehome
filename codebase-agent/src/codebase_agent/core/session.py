"""Unified session management: init = index + summaries + LSP warmup."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ExecutionMode, SandboxMode, DEFAULT_EXECUTION_MODE, DEFAULT_SANDBOX_MODE
from ..models import RepoIndex
from .indexer import build_index, is_index_cache_fresh, load_fresh_index, save_index_to_disk, start_watcher
from .lsp_client import PyrightLSP
from .mentions import MentionResolver

logger = logging.getLogger("codebase_agent.session")

_active_session: Session | None = None
_session_lock = threading.Lock()


@dataclass
class SessionConfig:
    """Configuration controlling which intelligence layers are active."""

    use_lsp: bool = True
    use_summaries: bool = True
    watch: bool = False
    execution_mode: ExecutionMode = DEFAULT_EXECUTION_MODE
    sandbox_mode: SandboxMode = DEFAULT_SANDBOX_MODE


@dataclass
class Session:
    """An active agent session with all intelligence layers initialized."""

    index: RepoIndex
    root_path: str
    mention_resolver: MentionResolver
    lsp: PyrightLSP | None = None
    summaries_built: bool = False
    config: SessionConfig = field(default_factory=SessionConfig)

    def shutdown(self) -> None:
        """Clean up session resources."""
        if self.lsp is not None:
            self.lsp.stop()
            self.lsp = None


def init_session(
    root_path: str,
    config: SessionConfig | None = None,
    profiler=None,
) -> Session:
    """Full session initialization: build index, generate summaries, start LSP.

    This is the primary entry point for session setup. It combines all
    intelligence layers into a single atomic operation.
    """
    global _active_session

    if config is None:
        config = SessionConfig()

    root = str(Path(root_path).resolve())

    # Phase 1: Build or load the index (tree-sitter + scanner)
    idx = load_fresh_index(root)
    if idx is None:
        idx = build_index(root, profiler=profiler)
        save_index_to_disk(idx, root)

    # Phase 2: Generate NL summaries
    summaries_built = False
    if config.use_summaries:
        from ..intelligence.summarizer import build_summaries
        build_summaries(idx, root)
        summaries_built = True

    # Phase 3: Start Pyright LSP with health check
    lsp: PyrightLSP | None = None
    if config.use_lsp:
        lsp = _start_lsp_checked(root)

    session = Session(
        index=idx,
        root_path=root,
        mention_resolver=MentionResolver.from_index(idx, root),
        lsp=lsp,
        summaries_built=summaries_built,
        config=config,
    )

    with _session_lock:
        if _active_session is not None:
            _active_session.shutdown()
        _active_session = session

    # Phase 4: Start file watcher if requested
    if config.watch:
        _start_watcher_thread(session)

    return session


def get_or_init_session(
    root_path: str,
    config: SessionConfig | None = None,
    profiler=None,
) -> Session:
    """Return the active session if it matches root_path, otherwise init a new one."""
    global _active_session
    root = str(Path(root_path).resolve())

    with _session_lock:
        if (
            _active_session is not None
            and _active_session.root_path == root
            and is_index_cache_fresh(root, _active_session.index)
        ):
            # Ensure LSP is still alive if config requires it
            effective_config = config or _active_session.config
            if effective_config.use_lsp and (_active_session.lsp is None or not _active_session.lsp.is_running):
                _active_session.lsp = _start_lsp_checked(root)
            return _active_session

    return init_session(root_path, config=config, profiler=profiler)


def _start_lsp_checked(root_path: str) -> PyrightLSP | None:
    """Start Pyright LSP with graceful fallback if unavailable."""
    if not PyrightLSP.is_available():
        logger.info("Pyright not installed; LSP layer disabled.")
        return None

    lsp = PyrightLSP(root_path)
    if lsp.start():
        logger.info("Pyright LSP started successfully.")
        return lsp

    logger.warning("Pyright LSP failed to start; continuing without LSP.")
    return None


def _start_watcher_thread(session: Session) -> None:
    """Start the file watcher in a daemon thread."""
    thread = threading.Thread(
        target=start_watcher,
        args=(
            session.root_path,
            session.index,
            lambda refreshed: session.mention_resolver.refresh(refreshed, session.root_path),
        ),
        daemon=True,
    )
    thread.start()
