"""Three-tier NL summary system: file, symbol, directory summaries."""

import hashlib
from collections import defaultdict
from pathlib import Path

import msgpack

from ..config import INDEX_DIR, SUMMARY_FILE
from ..models import (
    CachedSummary,
    DirectorySummary,
    FileSummary,
    RepoIndex,
    SymbolRecord,
    SymbolSummary,
)

SIDE_EFFECT_PATTERNS = [
    "write", "save", "send", "delete", "remove", "post", "put",
    "patch", "create", "insert", "update", "emit", "publish",
    "open", "close",
]

EXTERNAL_SERVICE_PATTERNS = [
    "requests", "httpx", "aiohttp", "boto3", "stripe",
    "redis", "celery", "kafka", "rabbitmq", "smtp",
]


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
        file_summary = _generate_file_summary(file_rec.path, facts)
        symbol_summaries = _generate_symbol_summaries(file_symbols, file_rec.path)

        file_summaries.append(file_summary)
        new_cache[file_rec.path] = CachedSummary(
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
                    facts.external_services.append(imp.module)
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
        data_models_touched=facts.data_models[:5], external_services=facts.external_services[:3],
        confidence=confidence, generated_from=generated_from,
    )


def _generate_purpose(facts, file_path):
    parts: list[str] = []
    if facts.has_test_markers:
        parts.append(f"Tests for {', '.join(facts.tested_modules[:2]) or 'related modules'}")
    if facts.has_route_decorators:
        parts.append(f"Defines {len(facts.routes)} API endpoints")
    if facts.main_classes:
        parts.append(f"Implements {', '.join(facts.main_classes[:2])}")
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
