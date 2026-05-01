"""Three-tier NL summary system: file, symbol, directory summaries."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

import msgpack

from ..config import INDEX_DIR, SUMMARY_BATCH_SIZE, SUMMARY_FILE, SUMMARY_LLM_MODEL
from ..models import (
    CachedSummary,
    DirectorySummary,
    FileSummary,
    RepoIndex,
    SymbolRecord,
    SymbolSummary,
)

logger = logging.getLogger(__name__)

SIDE_EFFECT_PATTERNS = [
    "write", "save", "send", "delete", "remove", "post", "put",
    "patch", "create", "insert", "update", "emit", "publish",
    "open", "close",
]

EXTERNAL_SERVICE_PATTERNS = [
    # HTTP clients
    "requests", "httpx", "aiohttp", "urllib3",
    # Cloud providers
    "boto3", "botocore", "google.cloud", "azure",
    # Databases (SQL)
    "sqlalchemy", "psycopg", "pymysql", "asyncpg", "aiomysql",
    "sqlite3", "alembic",
    # Databases (NoSQL)
    "pymongo", "motor", "elasticsearch", "opensearch",
    "cassandra", "couchdb",
    # Caching / queues
    "redis", "aioredis", "celery", "kafka", "confluent_kafka",
    "rabbitmq", "pika", "kombu", "dramatiq", "rq",
    # AI / LLM providers
    "openai", "anthropic", "cohere", "mistral", "groq",
    "litellm", "langchain", "llama_index",
    # Payments
    "stripe", "braintree", "paypalrestsdk",
    # Email / SMS / push
    "smtp", "sendgrid", "mailgun", "postmark",
    "twilio", "vonage", "firebase_admin",
    # Observability
    "sentry_sdk", "datadog", "newrelic", "opentelemetry",
    "prometheus_client", "statsd",
    # Auth / secrets
    "jwt", "authlib", "python_jose", "hvac",
    # Storage / CDN
    "paramiko", "fabric", "ftplib",
    # Web frameworks (indicates HTTP boundary)
    "fastapi", "flask", "django", "starlette", "tornado",
    "aiohttp.web", "grpc",
    # Supabase / Firebase / BaaS
    "supabase", "firebase",
]

ROUTE_DECORATOR_PATTERNS = [
    "app.get", "app.post", "app.put", "app.patch", "app.delete",
    "app.route", "app.options", "app.head",
    "router.get", "router.post", "router.put", "router.patch", "router.delete",
    "router.route", "router.options", "router.head",
    "blueprint.route", "blueprint.get", "blueprint.post",
    "api_view", "action",
    "route",
]


def _extract_route_path(decorator: str) -> str:
    """Extract the URL path from a route decorator string like '@app.get("/users")'."""
    start = decorator.find("(")
    if start == -1:
        return ""
    inner = decorator[start + 1:]
    for quote in ('"', "'"):
        qi = inner.find(quote)
        if qi != -1:
            end_q = inner.find(quote, qi + 1)
            if end_q != -1:
                return inner[qi + 1 : end_q]
    return ""


def build_summaries(
    index: RepoIndex,
    root_path: str,
    use_llm: bool = False,
) -> list[FileSummary]:
    """Generate summaries for all indexed files."""
    cache_dir = Path(root_path) / INDEX_DIR
    cached = _load_cached_summaries(str(cache_dir / SUMMARY_FILE))

    file_summaries: list[FileSummary] = []
    new_cache: dict[str, CachedSummary] = {}

    # Collect uncached files that need generation
    pending: list[tuple[str, str, _FactBundle, list]] = []

    for file_rec in index.files:
        abs_path = Path(root_path) / file_rec.path
        try:
            content = abs_path.read_bytes()
        except OSError:
            continue

        file_hash = hashlib.sha256(content).hexdigest()

        if file_rec.path in cached and cached[file_rec.path].file_hash == file_hash:
            entry = cached[file_rec.path]
            file_summaries.append(entry.file_summary)
            new_cache[file_rec.path] = entry
            continue

        file_symbols = [s for s in index.symbols if s.file_path == file_rec.path]
        file_imports = [i for i in index.imports if i.file_path == file_rec.path]
        facts = _extract_facts(file_rec.path, file_symbols, file_imports, index)
        pending.append((file_rec.path, file_hash, facts, file_symbols))

    if use_llm and pending:
        # Process in batches through the LLM
        for batch_start in range(0, len(pending), SUMMARY_BATCH_SIZE):
            batch = pending[batch_start : batch_start + SUMMARY_BATCH_SIZE]
            llm_batch = [(path, facts, syms) for path, _hash, facts, syms in batch]
            llm_results = _generate_llm_summaries_batch(llm_batch)

            for path, file_hash, facts, file_symbols in batch:
                if path in llm_results:
                    file_summary = _merge_llm_into_summary(path, facts, llm_results[path])
                else:
                    file_summary = _generate_file_summary(path, facts)
                symbol_summaries = _generate_symbol_summaries(file_symbols, path)

                file_summaries.append(file_summary)
                new_cache[path] = CachedSummary(
                    file_hash=file_hash,
                    file_summary=file_summary,
                    symbol_summaries=symbol_summaries,
                )
    else:
        # Heuristic-only path
        for path, file_hash, facts, file_symbols in pending:
            file_summary = _generate_file_summary(path, facts)
            symbol_summaries = _generate_symbol_summaries(file_symbols, path)

            file_summaries.append(file_summary)
            new_cache[path] = CachedSummary(
                file_hash=file_hash,
                file_summary=file_summary,
                symbol_summaries=symbol_summaries,
            )

    _save_cached_summaries(new_cache, str(cache_dir / SUMMARY_FILE))
    return file_summaries


def get_file_summary(index: RepoIndex, root_path: str, file_path: str) -> FileSummary | None:
    """Get or generate summary for a single file."""
    cache_dir = Path(root_path) / INDEX_DIR
    cached = _load_cached_summaries(str(cache_dir / SUMMARY_FILE))

    if file_path in cached:
        return cached[file_path].file_summary

    file_symbols = [s for s in index.symbols if s.file_path == file_path]
    file_imports = [i for i in index.imports if i.file_path == file_path]

    if not file_symbols and not file_imports:
        return None

    facts = _extract_facts(file_path, file_symbols, file_imports, index)
    return _generate_file_summary(file_path, facts)


def get_directory_summary(index: RepoIndex, root_path: str, dir_path: str) -> DirectorySummary:
    """Generate a summary for a directory from its child files."""
    dir_path = dir_path.rstrip("/")
    is_root = dir_path in (".", "")

    if is_root:
        child_files = list(index.files)
        child_symbols = list(index.symbols)
    else:
        child_files = [f for f in index.files if f.path.startswith(dir_path + "/")]
        child_symbols = [s for s in index.symbols if s.file_path.startswith(dir_path + "/")]

    contains: list[str] = []
    common_deps: set[str] = set()

    for f in child_files[:10]:
        file_symbols = [s for s in child_symbols if s.file_path == f.path]
        if file_symbols:
            main = file_symbols[0]
            contains.append(f"{main.name} in {Path(f.path).name}")

    if is_root:
        file_imports = list(index.imports)
    else:
        file_imports = [i for i in index.imports if i.file_path.startswith(dir_path + "/")]
    for imp in file_imports:
        if imp.module and not imp.module.startswith(dir_path.replace("/", ".")):
            parts = imp.module.split(".")
            if parts:
                common_deps.add(parts[0])

    summary_text = _infer_directory_role(dir_path, child_files, child_symbols)

    return DirectorySummary(
        path=dir_path,
        summary=summary_text,
        contains=contains[:5],
        common_dependencies=sorted(common_deps)[:5],
        file_count=len(child_files),
        symbol_count=len(child_symbols),
    )


def search_summaries(
    index: RepoIndex,
    root_path: str,
    query: str,
    max_results: int = 10,
) -> list[dict]:
    """Keyword search across summary fields."""
    cache_dir = Path(root_path) / INDEX_DIR
    cached = _load_cached_summaries(str(cache_dir / SUMMARY_FILE))
    q = query.lower()

    scored: list[tuple[float, str, FileSummary]] = []
    for path, entry in cached.items():
        s = entry.file_summary
        score = 0.0
        if q in s.purpose.lower():
            score += 1.0
        for r in s.responsibilities:
            if q in r.lower():
                score += 0.5
        for sym in s.main_symbols:
            if q in sym.lower():
                score += 0.3
        for se in s.side_effects:
            if q in se.lower():
                score += 0.2
        for es in s.external_services:
            if q in es.lower():
                score += 0.2
        if score > 0:
            scored.append((score, path, s))

    scored.sort(key=lambda x: -x[0])
    return [
        {"path": path, "purpose": s.purpose, "score": score}
        for score, path, s in scored[:max_results]
    ]


class _FactBundle:
    def __init__(self) -> None:
        self.main_classes: list[str] = []
        self.main_functions: list[str] = []
        self.has_route_decorators: bool = False
        self.has_test_markers: bool = False
        self.routes: list[str] = []
        self.tested_modules: list[str] = []
        self.depends_on: list[str] = []
        self.used_by: list[str] = []
        self.side_effects: list[str] = []
        self.external_services: list[str] = []
        self.data_models: list[str] = []
        self.decorators: list[str] = []
        self.docstrings: list[str] = []


def _extract_facts(file_path, symbols, imports, index):
    facts = _FactBundle()
    for sym in symbols:
        if sym.kind == "class":
            facts.main_classes.append(sym.name)
        elif sym.kind in ("function", "async_function"):
            facts.main_functions.append(sym.name)
        if sym.docstring:
            facts.docstrings.append(sym.docstring)
    for imp in imports:
        if imp.module:
            facts.depends_on.append(imp.module)
            for pattern in EXTERNAL_SERVICE_PATTERNS:
                if pattern in imp.module.lower():
                    # Deduplicate by top-level service name (e.g. all boto3.* -> "boto3")
                    top_level = pattern
                    if top_level not in facts.external_services:
                        facts.external_services.append(top_level)
                    break
    for sym in symbols:
        ref_files = index.name_reference_map.get(sym.name, [])
        for rf in ref_files:
            if rf != file_path and rf not in facts.used_by:
                facts.used_by.append(rf)
    for sym in symbols:
        name_lower = sym.name.lower()
        for pattern in SIDE_EFFECT_PATTERNS:
            if pattern in name_lower:
                facts.side_effects.append(f"{sym.name} may {pattern}")
                break
    for sym in symbols:
        for dec in getattr(sym, "decorators", []):
            dec_lower = dec.lower().lstrip("@")
            for pattern in ROUTE_DECORATOR_PATTERNS:
                if dec_lower.startswith(pattern):
                    facts.has_route_decorators = True
                    route_path = _extract_route_path(dec)
                    if route_path:
                        facts.routes.append(route_path)
                    else:
                        facts.routes.append(f"[{sym.name}]")
                    facts.decorators.append(dec)
                    break
    if "test" in file_path.lower():
        facts.has_test_markers = True
        for imp in imports:
            if imp.module:
                facts.tested_modules.append(imp.module)
    return facts


def _generate_file_summary(file_path, facts):
    purpose = _generate_purpose(facts, file_path)
    responsibilities = _generate_responsibilities(facts)
    main_symbols = facts.main_classes[:3] + facts.main_functions[:3]
    generated_from = ["imports", "function_signatures"]
    if facts.docstrings:
        generated_from.append("docstrings")
    confidence = 0.5
    if facts.docstrings:
        confidence += 0.2
    if facts.main_classes or facts.main_functions:
        confidence += 0.15
    confidence = min(confidence, 1.0)
    return FileSummary(
        path=file_path, purpose=purpose, responsibilities=responsibilities,
        main_symbols=main_symbols, depends_on=facts.depends_on[:5],
        used_by=facts.used_by[:5], side_effects=facts.side_effects[:5],
        data_models_touched=facts.data_models[:5], external_services=facts.external_services[:8],
        confidence=confidence, generated_from=generated_from,
    )


def _generate_purpose(facts, file_path):
    parts: list[str] = []
    if facts.has_test_markers:
        parts.append(f"Tests for {', '.join(facts.tested_modules[:2]) or 'related modules'}")
    if facts.has_route_decorators:
        parts.append(f"Defines {len(facts.routes)} API endpoints")
    if facts.main_classes:
        parts.append(f"Implements {', '.join(facts.main_classes[:3])}")
    elif facts.main_functions:
        parts.append(f"Provides {', '.join(facts.main_functions[:3])}")
    if not parts:
        parts.append(f"Module at {file_path}")
    return ". ".join(parts) + "."


def _generate_responsibilities(facts):
    resps: list[str] = []
    for cls in facts.main_classes[:2]:
        resps.append(f"Defines {cls} class")
    for func in facts.main_functions[:3]:
        resps.append(f"Provides {func} function")
    for se in facts.side_effects[:2]:
        resps.append(se)
    return resps[:5]


def _generate_symbol_summaries(symbols, file_path):
    summaries = []
    for sym in symbols[:10]:
        summary_text = sym.docstring or f"{sym.kind.title()} {sym.name}"
        summaries.append(SymbolSummary(
            symbol=sym.qualified_name, kind=sym.kind, file_path=file_path,
            signature=sym.signature or "", summary=summary_text[:200],
            confidence=0.7 if sym.docstring else 0.4,
        ))
    return summaries


def _infer_directory_role(dir_path, files, symbols):
    name = Path(dir_path).name.lower()
    role_map = {
        "api": "HTTP route handlers", "routes": "HTTP route handlers",
        "views": "HTTP route handlers", "models": "Data models",
        "schemas": "Data schemas", "services": "Business logic",
        "core": "Core business logic", "tests": "Test suite",
        "utils": "Shared utilities", "helpers": "Helper functions",
        "config": "Configuration", "migrations": "Database migrations",
        "middleware": "Request middleware",
    }
    role = role_map.get(name, "")
    if role:
        return f"{role} ({len(files)} files, {len(symbols)} symbols)."
    return f"Contains {len(files)} files with {len(symbols)} symbols."


def _load_cached_summaries(path):
    try:
        packed = Path(path).read_bytes()
        data = msgpack.unpackb(packed, raw=False)
        return {k: CachedSummary.model_validate(v) for k, v in data.items()}
    except (OSError, msgpack.UnpackException, Exception):
        return {}


def _save_cached_summaries(cache, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.model_dump(mode="python") for k, v in cache.items()}
    packed = msgpack.packb(data, use_bin_type=True, default=str)
    Path(path).write_bytes(packed)


# ---------------------------------------------------------------------------
# LLM-enhanced summary generation
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = (
    "You are a code analyst. For each Python file described below, write a concise "
    "summary that explains the file's purpose and main responsibilities. Focus on "
    "design intent and architectural role, not just listing symbols.\n\n"
    "Respond with JSON only. The JSON must have a single key \"files\" whose value "
    "is a list of objects, each with keys \"path\" (string), \"purpose\" (string, "
    "1-2 sentences), and \"responsibilities\" (list of 2-5 short strings)."
)


def _get_openai_client():
    """Lazily create an OpenAI client. Returns None if unavailable."""
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None


def _build_llm_prompt(batch: list[tuple[str, _FactBundle]]) -> str:
    """Format a batch of files+facts into a compact user prompt."""
    parts: list[str] = []
    for i, (path, facts) in enumerate(batch, 1):
        lines = [f"File {i}: {path}"]
        if facts.main_classes:
            lines.append(f"- Classes: {', '.join(facts.main_classes[:5])}")
        if facts.main_functions:
            lines.append(f"- Functions: {', '.join(facts.main_functions[:5])}")
        deps = facts.depends_on[:5]
        if deps:
            lines.append(f"- Imports: {', '.join(deps)}")
        if facts.docstrings:
            doc = facts.docstrings[0][:150]
            lines.append(f'- Docstring: "{doc}"')
        if facts.has_test_markers:
            lines.append("- This is a test file.")
        if facts.has_route_decorators:
            lines.append(f"- Defines {len(facts.routes)} HTTP route(s): {', '.join(facts.routes[:5])}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _parse_llm_response(
    raw_text: str,
    paths: list[str],
) -> dict[str, tuple[str, list[str]]]:
    """Parse JSON from the LLM into {path: (purpose, responsibilities)}.

    Returns only the paths that were successfully parsed.
    """
    result: dict[str, tuple[str, list[str]]] = {}
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return result

    files_list = data.get("files", [])
    if not isinstance(files_list, list):
        return result

    for entry in files_list:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path", "")
        purpose = entry.get("purpose", "")
        resps = entry.get("responsibilities", [])
        if p and purpose and isinstance(resps, list):
            resps = [r for r in resps if isinstance(r, str)][:5]
            result[p] = (str(purpose), resps)
    return result


def _generate_llm_summaries_batch(
    batch: list[tuple[str, _FactBundle, list]],
) -> dict[str, tuple[str, list[str]]]:
    """Call the LLM for a batch of files and return enriched purpose/responsibilities.

    Each item in *batch* is (file_path, facts, symbols).
    Returns {path: (purpose, responsibilities)} for successfully enriched files.
    On any failure, returns an empty dict (caller falls back to heuristic).
    """
    client = _get_openai_client()
    if client is None:
        return {}

    prompt_batch = [(path, facts) for path, facts, _syms in batch]
    user_prompt = _build_llm_prompt(prompt_batch)
    paths = [path for path, _f, _s in batch]

    try:
        response = client.chat.completions.create(
            model=SUMMARY_LLM_MODEL,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        return _parse_llm_response(raw, paths)
    except Exception as exc:
        logger.debug("LLM summary batch failed: %s", exc)
        return {}


def _merge_llm_into_summary(
    file_path: str,
    facts: _FactBundle,
    llm_result: tuple[str, list[str]],
) -> FileSummary:
    """Build a FileSummary using LLM-generated purpose/responsibilities
    combined with heuristic structural fields."""
    purpose, responsibilities = llm_result
    main_symbols = facts.main_classes[:3] + facts.main_functions[:3]
    return FileSummary(
        path=file_path,
        purpose=purpose,
        responsibilities=responsibilities,
        main_symbols=main_symbols,
        depends_on=facts.depends_on[:5],
        used_by=facts.used_by[:5],
        side_effects=facts.side_effects[:5],
        data_models_touched=facts.data_models[:5],
        external_services=facts.external_services[:3],
        confidence=0.9,
        generated_from=["llm", "facts"],
    )
