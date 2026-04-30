"""Smart indexer with multi-layer caching: in-memory, per-file hash, msgpack, watcher."""

import hashlib
import threading
from collections import defaultdict
from pathlib import Path

import msgpack

from ..config import INDEX_DIR, INDEX_FILE, HASH_FILE, SUPPORTED_EXTENSIONS
from ..models import FileRecord, ImportRecord, ParseResult, RepoIndex, SymbolRecord
from .scanner import scan_repo
from .ts_parser import parse_file

_session_index: RepoIndex | None = None
_session_lock = threading.Lock()


def get_or_build_index(root_path: str) -> RepoIndex:
    """Return the session index (in-memory singleton) or build/load one."""
    global _session_index
    with _session_lock:
        root = str(Path(root_path).resolve())
        if (
            _session_index is not None
            and _session_index.root_path == root
            and is_index_cache_fresh(root, _session_index)
        ):
            return _session_index

        idx = load_fresh_index(root)
        if idx is not None:
            _session_index = idx
            return idx

        idx = build_index(root)
        save_index_to_disk(idx, root)
        _session_index = idx
        return idx


def load_fresh_index(root_path: str) -> RepoIndex | None:
    """Load the cached index only when it matches the current repo contents."""
    root = str(Path(root_path).resolve())
    cache_dir = Path(root) / INDEX_DIR
    index_path = cache_dir / INDEX_FILE
    if not index_path.exists():
        return None

    idx = load_index(str(index_path))
    if idx.root_path != root:
        return None
    if not is_index_cache_fresh(root, idx):
        return None
    return idx


def is_index_cache_fresh(root_path: str, index: RepoIndex | None = None) -> bool:
    """Return True when persisted hashes match the current scanned files."""
    root = str(Path(root_path).resolve())
    cache_dir = Path(root) / INDEX_DIR
    cached_hashes = _load_hashes(str(cache_dir / HASH_FILE))
    if not cached_hashes:
        return False

    files = scan_repo(root)
    current_paths = {f.path for f in files}
    if set(cached_hashes) != current_paths:
        return False
    if index is not None and {f.path for f in index.files} != current_paths:
        return False

    for file_rec in files:
        abs_path = Path(root) / file_rec.path
        try:
            content = abs_path.read_bytes()
        except OSError:
            return False
        file_hash = hashlib.sha256(content).hexdigest()
        if cached_hashes.get(file_rec.path) != file_hash:
            return False
    return True


def build_index(root_path: str, profiler=None) -> RepoIndex:
    """Build a full index with incremental per-file hash caching."""
    import time as _time

    root = str(Path(root_path).resolve())
    cache_dir = Path(root) / INDEX_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    if profiler:
        profiler.start_build()

    cached_hashes = _load_hashes(str(cache_dir / HASH_FILE))
    cached_results: dict[str, ParseResult] = {}
    cache_hit = bool(cached_hashes)

    scan_start = _time.perf_counter()
    files = scan_repo(root)
    scan_ms = (_time.perf_counter() - scan_start) * 1000

    all_symbols: list[SymbolRecord] = []
    all_imports: list[ImportRecord] = []
    new_hashes: dict[str, str] = {}

    # Phase 1: parse all files, collect symbols and imports
    parse_start = _time.perf_counter()
    for file_rec in files:
        abs_path = str(Path(root) / file_rec.path)
        try:
            content = Path(abs_path).read_bytes()
        except OSError:
            continue

        file_hash = hashlib.sha256(content).hexdigest()
        new_hashes[file_rec.path] = file_hash

        if file_hash == cached_hashes.get(file_rec.path):
            result = cached_results.get(file_rec.path)
            if result is None:
                result = parse_file(abs_path)
                cached_results[file_rec.path] = result
        else:
            result = parse_file(abs_path)
            cached_results[file_rec.path] = result

        # Normalize file_path to relative (matching FileRecord.path)
        for sym in result.symbols:
            sym.file_path = file_rec.path
        for imp in result.imports:
            imp.file_path = file_rec.path

        all_symbols.extend(result.symbols)
        all_imports.extend(result.imports)
    parse_ms = (_time.perf_counter() - parse_start) * 1000

    # Build known symbol name set for phase 2
    known_symbols = {s.name for s in all_symbols}

    # Phase 2: build name_reference_map from identifier_refs
    graph_start = _time.perf_counter()
    name_reference_map: dict[str, list[str]] = defaultdict(list)
    for file_rec in files:
        result = cached_results.get(file_rec.path)
        if result is None:
            continue
        for ref_name in result.identifier_refs:
            if ref_name in known_symbols:
                name_reference_map[ref_name].append(file_rec.path)

    # Build test_map
    test_map: dict[str, list[str]] = defaultdict(list)
    for file_rec in files:
        if _is_test_file(file_rec.path):
            result = cached_results.get(file_rec.path)
            if result is None:
                continue
            for imp in result.imports:
                if imp.module:
                    source_file = _module_to_file(imp.module, root, files)
                    if source_file:
                        test_map[source_file].append(file_rec.path)
    graph_ms = (_time.perf_counter() - graph_start) * 1000

    # Save hashes
    _save_hashes(new_hashes, str(cache_dir / HASH_FILE))

    index = RepoIndex(
        root_path=root,
        files=files,
        symbols=all_symbols,
        imports=all_imports,
        test_map=dict(test_map),
        name_reference_map=dict(name_reference_map),
    )

    if profiler:
        profiler.end_build(
            file_count=len(files),
            symbol_count=len(all_symbols),
            import_count=len(all_imports),
            index_size_bytes=0,
            cache_hit=cache_hit,
            scan_ms=scan_ms,
            parse_ms=parse_ms,
            graph_ms=graph_ms,
        )

    return index


def save_index_to_disk(index: RepoIndex, root_path: str) -> None:
    """Serialize the index to msgpack on disk."""
    cache_dir = Path(root_path) / INDEX_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = index.model_dump(mode="python")
    packed = msgpack.packb(data, use_bin_type=True, default=str)
    (cache_dir / INDEX_FILE).write_bytes(packed)


def load_index(index_path: str) -> RepoIndex:
    """Load a previously saved index from msgpack."""
    packed = Path(index_path).read_bytes()
    data = msgpack.unpackb(packed, raw=False)
    return RepoIndex.model_validate(data)


def start_watcher(root_path: str, index: RepoIndex) -> None:
    """Start a background file watcher for incremental re-indexing."""
    try:
        from watchfiles import watch
    except ImportError:
        return

    root = Path(root_path).resolve()
    for changes in watch(str(root)):
        for _change_type, path in changes:
            if Path(path).suffix in SUPPORTED_EXTENSIONS:
                _update_index_for_file(index, path, root)


def _update_index_for_file(index: RepoIndex, abs_path: str, root: Path) -> None:
    """Refresh the active index after a file change and persist the new cache."""
    refreshed = build_index(str(root))
    save_index_to_disk(refreshed, str(root))
    _replace_index_contents(index, refreshed)


def _replace_index_contents(target: RepoIndex, source: RepoIndex) -> None:
    """Mutate an existing RepoIndex so sessions keep a live reference."""
    target.root_path = source.root_path
    target.files = source.files
    target.symbols = source.symbols
    target.imports = source.imports
    target.test_map = source.test_map
    target.name_reference_map = source.name_reference_map


def _is_test_file(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def _module_to_file(module: str, root: str, files: list[FileRecord]) -> str | None:
    """Convert a module path like 'app.models' to a file path like 'app/models.py'."""
    candidate = module.replace(".", "/") + ".py"
    for f in files:
        if f.path == candidate or f.path.endswith("/" + candidate):
            return f.path
    pkg_init = module.replace(".", "/") + "/__init__.py"
    for f in files:
        if f.path == pkg_init or f.path.endswith("/" + pkg_init):
            return f.path
    return None


def _load_hashes(path: str) -> dict[str, str]:
    try:
        packed = Path(path).read_bytes()
        return msgpack.unpackb(packed, raw=False)
    except (OSError, msgpack.UnpackException):
        return {}


def _save_hashes(hashes: dict[str, str], path: str) -> None:
    packed = msgpack.packb(hashes, use_bin_type=True)
    Path(path).write_bytes(packed)
