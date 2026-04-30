"""Search module: ripgrep primary, Python re fallback, ranked symbol search."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from ..models import RepoIndex, SymbolRecord


def search_text(
    root_path: str,
    query: str,
    file_glob: str = "*.py",
    max_results: int = 50,
) -> list[dict]:
    """Search for text in files. Uses ripgrep if available, else Python re."""
    if shutil.which("rg"):
        return _search_with_ripgrep(root_path, query, file_glob, max_results)
    return _search_with_python(root_path, query, file_glob, max_results)


def _search_with_ripgrep(
    root_path: str,
    query: str,
    file_glob: str,
    max_results: int,
) -> list[dict]:
    cmd = [
        "rg", "--json",
        "--glob", file_glob,
        "--max-count", str(max_results),
        query,
        root_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _search_with_python(root_path, query, file_glob, max_results)

    matches = []
    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "match":
            data = obj["data"]
            path_obj = data.get("path", {})
            path_text = path_obj.get("text", "") if isinstance(path_obj, dict) else str(path_obj)
            try:
                rel = str(Path(path_text).relative_to(root_path))
            except ValueError:
                rel = path_text
            line_number = data.get("line_number", 0)
            lines = data.get("lines", {})
            context = lines.get("text", "").rstrip() if isinstance(lines, dict) else ""
            matches.append({
                "file": rel,
                "line": line_number,
                "context": context,
            })
            if len(matches) >= max_results:
                break

    return matches


def _search_with_python(
    root_path: str,
    query: str,
    file_glob: str,
    max_results: int,
) -> list[dict]:
    import fnmatch

    root = Path(root_path)
    try:
        regex = re.compile(query)
    except re.error:
        regex = re.compile(re.escape(query))

    matches = []
    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        if not fnmatch.fnmatch(filepath.name, file_glob):
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                rel = str(filepath.relative_to(root))
                matches.append({
                    "file": rel,
                    "line": lineno,
                    "context": line.rstrip(),
                })
                if len(matches) >= max_results:
                    return matches

    return matches


def search_symbols(index: RepoIndex, query: str, max_results: int = 20) -> list[dict]:
    """Ranked symbol search: exact > prefix > substring > docstring.

    If query is empty, returns all symbols (useful for full-project scans).
    """
    q = query.lower().strip()

    # Empty query: return all symbols (no ranking needed)
    if not q:
        results = []
        for sym in index.symbols[:max_results]:
            results.append({
                "name": sym.name,
                "qualified_name": sym.qualified_name,
                "kind": sym.kind,
                "file": sym.file_path,
                "line": sym.line_start,
                "signature": sym.signature,
                "score": 1.0,
            })
        return results

    scored: list[tuple[float, SymbolRecord]] = []

    for sym in index.symbols:
        name_lower = sym.name.lower()
        qual_lower = sym.qualified_name.lower()

        if name_lower == q:
            score = 1.0
        elif name_lower.startswith(q):
            score = 0.8
        elif q in qual_lower:
            score = 0.6
        elif q in name_lower:
            score = 0.5
        elif sym.docstring and q in sym.docstring.lower():
            score = 0.3
        else:
            continue

        scored.append((score, sym))

    scored.sort(key=lambda x: -x[0])
    results = []
    for score, sym in scored[:max_results]:
        results.append({
            "name": sym.name,
            "qualified_name": sym.qualified_name,
            "kind": sym.kind,
            "file": sym.file_path,
            "line": sym.line_start,
            "signature": sym.signature,
            "score": score,
        })
    return results


def search_files(index: RepoIndex, query: str, max_results: int = 20) -> list[dict]:
    """Search file paths by keyword."""
    q = query.lower()
    results = []
    for f in index.files:
        if q in f.path.lower():
            results.append({
                "path": f.path,
                "size_bytes": f.size_bytes,
                "line_count": f.line_count,
            })
            if len(results) >= max_results:
                break
    return results
