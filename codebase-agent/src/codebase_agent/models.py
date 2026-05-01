"""Pydantic data models for the codebase navigation agent."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FileRecord(BaseModel):
    path: str
    language: str = "python"
    size_bytes: int = 0
    line_count: int = 0


class SymbolRecord(BaseModel):
    name: str
    qualified_name: str
    kind: Literal["class", "function", "method", "async_function", "async_method"]
    file_path: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    parent: str | None = None
    decorators: list[str] = Field(default_factory=list)


class ImportRecord(BaseModel):
    file_path: str
    module: str | None = None
    imported_name: str | None = None
    alias: str | None = None
    is_relative: bool = False
    level: int = 0


class ReferenceRecord(BaseModel):
    symbol_name: str
    file_path: str
    line: int
    context: str = ""


class ParseResult(BaseModel):
    symbols: list[SymbolRecord] = []
    imports: list[ImportRecord] = []
    identifier_refs: list[str] = []


class RepoIndex(BaseModel):
    root_path: str
    files: list[FileRecord] = []
    symbols: list[SymbolRecord] = []
    imports: list[ImportRecord] = []
    test_map: dict[str, list[str]] = Field(default_factory=dict)
    name_reference_map: dict[str, list[str]] = Field(default_factory=dict)


class RepoMapNode(BaseModel):
    path: str
    type: Literal["directory", "file"]
    role: str | None = None
    summary: str | None = None
    file_count: int | None = None
    key_symbols: list[str] = Field(default_factory=list)
    children: list[RepoMapNode] = Field(default_factory=list)


class CallGraphNode(BaseModel):
    symbol: str
    file: str
    line: int
    resolution: Literal["exact", "heuristic", "unresolved"]
    calls: list[CallGraphNode] = Field(default_factory=list)


class SymbolCandidate(BaseModel):
    qualified_name: str
    kind: str
    file_path: str
    line: int
    signature: str | None = None
    confidence: float = 0.0
    reason: str = ""


class DisambiguatedResult(BaseModel):
    symbol: str
    candidates: list[SymbolCandidate] = Field(default_factory=list)
    disambiguation_needed: bool = False
    resolution_method: str = ""


class FileSummary(BaseModel):
    path: str
    purpose: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    main_symbols: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    data_models_touched: list[str] = Field(default_factory=list)
    external_services: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    generated_from: list[str] = Field(default_factory=list)


class SymbolSummary(BaseModel):
    symbol: str
    kind: str
    file_path: str
    signature: str = ""
    summary: str = ""
    side_effects: list[str] = Field(default_factory=list)
    raises: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class DirectorySummary(BaseModel):
    path: str
    summary: str = ""
    contains: list[str] = Field(default_factory=list)
    common_dependencies: list[str] = Field(default_factory=list)
    file_count: int = 0
    symbol_count: int = 0


class CachedSummary(BaseModel):
    file_hash: str
    file_summary: FileSummary
    symbol_summaries: list[SymbolSummary] = Field(default_factory=list)


class MentionedFile(BaseModel):
    path: str
    content_preview: str = ""
    symbols: list[str] = Field(default_factory=list)


class ParsedQuery(BaseModel):
    raw_query: str
    clean_query: str = ""
    mentioned_files: list[MentionedFile] = Field(default_factory=list)


# --- Logging / Tracing models ---


class TokenSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    by_tool: dict[str, int] = Field(default_factory=dict)


class TokenHotspot(BaseModel):
    tool_name: str
    total_tokens: int = 0
    call_count: int = 0
    avg_tokens_per_call: float = 0.0
    pct_of_total: float = 0.0


class ToolTrace(BaseModel):
    tool_name: str
    args: dict = Field(default_factory=dict)
    result_size_bytes: int = 0
    result_token_estimate: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error: str | None = None
    timestamp: datetime | None = None
    subtask_id: str | None = None
    was_useful: bool | None = None


class Span(BaseModel):
    span_id: str
    parent_id: str | None = None
    name: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    children: list[Span] = Field(default_factory=list)


class IndexProfile(BaseModel):
    scan_duration_ms: float = 0.0
    parse_duration_ms: float = 0.0
    graph_build_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    file_count: int = 0
    symbol_count: int = 0
    import_count: int = 0
    index_size_bytes: int = 0
    cache_hit: bool = False
    slowest_files: list[tuple[str, float]] = Field(default_factory=list)


class CostEstimate(BaseModel):
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    model: str = ""
    projected_daily_cost_usd: float | None = None


class UserSummary(BaseModel):
    question_type: str = ""
    files_analyzed: int = 0
    symbols_found: int = 0
    tools_called: int = 0
    duration_seconds: float = 0.0
    confidence: str = ""
