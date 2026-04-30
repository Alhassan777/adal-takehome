"""15+ agent-facing tool functions with hybrid LSP/tree-sitter resolution."""

from pathlib import Path
from typing import Literal

import networkx as nx

from ..core.graph import (
    build_dependency_graph,
    get_dependencies,
    get_dependents,
    get_files_referencing,
    get_test_files,
    get_transitive_dependents,
)
from ..core.lsp_client import PyrightLSP
from ..models import (
    CallGraphNode,
    DisambiguatedResult,
    RepoIndex,
    RepoMapNode,
    SymbolCandidate,
    SymbolRecord,
)
from ..core.search import search_files, search_symbols, search_text
from .summarizer import (
    get_directory_summary as _get_dir_summary,
    get_file_summary as _get_file_summary,
    search_summaries as _search_summaries,
)
from ..core.ts_parser import parse_file

_lsp_instance: PyrightLSP | None = None


def _get_lsp(root_path: str, lsp: PyrightLSP | None = None) -> PyrightLSP | None:
    """Get an LSP instance. Prefers a passed-in session LSP, falls back to global."""
    global _lsp_instance
    if lsp is not None and lsp.is_running:
        return lsp
    if _lsp_instance is not None and _lsp_instance.is_running:
        return _lsp_instance
    new_lsp = PyrightLSP(root_path)
    if new_lsp.start():
        _lsp_instance = new_lsp
        return new_lsp
    return None


def repo_map(root_path, index, depth=2, with_summaries=False):
    """Hierarchical annotated repo map."""
    root = Path(root_path).resolve()
    tree = _build_map_node(str(root), index, "", depth, with_summaries, root_path)
    return tree.model_dump()


def _build_map_node(abs_root, index, rel_path, depth, with_summaries, root_path):
    current = Path(abs_root) / rel_path if rel_path else Path(abs_root)
    if current.is_file():
        file_symbols = [s for s in index.symbols if s.file_path == rel_path]
        return RepoMapNode(path=rel_path, type="file", key_symbols=[s.name for s in file_symbols[:5]])

    children_nodes = []
    child_files = [f for f in index.files if _is_direct_child(f.path, rel_path)]
    child_dirs = _get_child_dirs(index, rel_path)

    if depth > 0:
        for d in sorted(child_dirs):
            children_nodes.append(_build_map_node(abs_root, index, d, depth - 1, with_summaries, root_path))
        for f in child_files:
            file_symbols = [s for s in index.symbols if s.file_path == f.path]
            children_nodes.append(RepoMapNode(path=f.path, type="file", key_symbols=[s.name for s in file_symbols[:5]]))

    if rel_path:
        all_under = [f for f in index.files if f.path.startswith(rel_path + "/")]
    else:
        all_under = list(index.files)
    file_count = len(all_under)
    role = _infer_role(rel_path)

    summary = None
    if with_summaries and rel_path:
        ds = _get_dir_summary(index, root_path, rel_path)
        summary = ds.summary if ds else None

    dir_symbols = [s for s in index.symbols if (s.file_path.startswith(rel_path + "/") if rel_path else True)]
    ref_counts = [(len(index.name_reference_map.get(s.name, [])), s.name) for s in dir_symbols]
    ref_counts.sort(key=lambda x: -x[0])
    key_syms = [name for _, name in ref_counts[:5]]

    return RepoMapNode(
        path=rel_path or ".", type="directory", role=role, summary=summary,
        file_count=file_count, key_symbols=key_syms, children=children_nodes,
    )


def _is_direct_child(file_path, dir_path):
    if not dir_path:
        return "/" not in file_path
    if not file_path.startswith(dir_path + "/"):
        return False
    return "/" not in file_path[len(dir_path) + 1:]


def _get_child_dirs(index, parent):
    dirs = set()
    prefix = parent + "/" if parent else ""
    for f in index.files:
        if prefix and not f.path.startswith(prefix):
            continue
        remainder = f.path[len(prefix):]
        if "/" in remainder:
            dirs.add(prefix + remainder.split("/")[0])
    return dirs


def _infer_role(dir_path):
    if not dir_path:
        return None
    name = Path(dir_path).name.lower()
    roles = {
        "api": "HTTP route handlers", "routes": "HTTP route handlers",
        "endpoints": "HTTP route handlers", "views": "HTTP route handlers",
        "models": "data models", "schemas": "data models",
        "services": "business logic", "core": "business logic",
        "tests": "test suite", "utils": "shared utilities",
        "helpers": "shared utilities", "config": "configuration",
        "migrations": "database migrations", "middleware": "request middleware",
        "scripts": "CLI / scripts", "cli": "CLI / scripts",
    }
    return roles.get(name)


def list_tree(root_path, index, depth=3):
    """Compact file tree listing."""
    files = [f.path for f in index.files]
    tree = {}
    for f in files:
        parts = f.split("/")
        if len(parts) > depth:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    return {"tree": tree, "total_files": len(index.files)}


def search_text_tool(root_path, query, file_glob="*.py"):
    results = search_text(root_path, query, file_glob)
    return {"query": query, "matches": results, "count": len(results)}


def search_symbols_tool(index, query):
    results = search_symbols(index, query)
    return {"query": query, "symbols": results, "count": len(results)}


def get_definition(root_path, index, symbol_name, context_file=None, context_position=None, lsp=None):
    graph = build_dependency_graph(index)
    resolved_lsp = _get_lsp(root_path, lsp)
    result = resolve_symbol(symbol_name, index, graph, context_file=context_file, context_position=context_position, lsp=resolved_lsp)
    if not result.candidates:
        return {"symbol": symbol_name, "found": False, "candidates": []}
    top = result.candidates[0]
    snippet = _read_lines(root_path, top.file_path, top.line, top.line + 10)
    return {
        "symbol": symbol_name, "found": True,
        "definition": {"qualified_name": top.qualified_name, "kind": top.kind, "file": top.file_path, "line": top.line, "signature": top.signature, "snippet": snippet},
        "disambiguation_needed": result.disambiguation_needed, "resolution_method": result.resolution_method,
        "all_candidates": [c.model_dump() for c in result.candidates],
    }


def find_references(root_path, index, symbol_name, lsp=None):
    resolved_lsp = _get_lsp(root_path, lsp)
    if resolved_lsp and resolved_lsp.is_running:
        candidates = [s for s in index.symbols if s.name == symbol_name]
        if candidates:
            sym = candidates[0]
            abs_path = str(Path(root_path) / sym.file_path)
            refs = resolved_lsp.find_references(abs_path, sym.line_start - 1, 0)
            if refs:
                return {"symbol": symbol_name, "references": refs, "count": len(refs), "method": "lsp"}
    ref_files = index.name_reference_map.get(symbol_name, [])
    text_refs = search_text(root_path, r"\b" + symbol_name + r"\b")
    return {"symbol": symbol_name, "reference_files": ref_files, "text_matches": text_refs[:20], "count": len(ref_files), "method": "name_reference_map+ripgrep"}


def read_snippet(root_path, file_path, start_line, end_line):
    snippet = _read_lines(root_path, file_path, start_line, end_line)
    return {"file": file_path, "start_line": start_line, "end_line": end_line, "content": snippet}


def get_imports(index, file_path):
    file_imports = [i for i in index.imports if i.file_path == file_path]
    return {"file": file_path, "imports": [i.model_dump() for i in file_imports], "count": len(file_imports)}


def trace_module(root_path, index, file_path):
    graph = build_dependency_graph(index)
    return {"file": file_path, "depends_on": get_dependencies(graph, file_path), "depended_by": get_dependents(graph, file_path), "test_files": get_test_files(graph, file_path)}


def get_call_graph(root_path, index, symbol_name, depth=1):
    candidates = [s for s in index.symbols if s.name == symbol_name or s.qualified_name == symbol_name]
    if not candidates:
        return {"symbol": symbol_name, "found": False, "calls": []}
    sym = candidates[0]
    abs_path = str(Path(root_path) / sym.file_path)
    call_names = []
    try:
        content = Path(abs_path).read_text()
        lines = content.splitlines()
        func_text = "\n".join(lines[sym.line_start - 1:sym.line_end])
        import re
        calls = re.findall(r'(\w+)\s*\(', func_text)
        call_names = [c for c in calls if c != sym.name and c[0].islower()]
    except (OSError, IndexError):
        pass
    call_nodes = []
    for call_name in call_names[:10]:
        target = next((s for s in index.symbols if s.name == call_name), None)
        if target:
            call_nodes.append({"symbol": target.qualified_name, "file": target.file_path, "line": target.line_start, "resolution": "heuristic"})
        else:
            call_nodes.append({"symbol": call_name, "file": "", "line": 0, "resolution": "unresolved"})
    return {"symbol": sym.qualified_name, "file": sym.file_path, "line": sym.line_start, "calls": call_nodes}


def find_tests(index, file_or_symbol):
    if "/" in file_or_symbol or file_or_symbol.endswith(".py"):
        test_files = index.test_map.get(file_or_symbol, [])
        return {"target": file_or_symbol, "test_files": test_files, "count": len(test_files), "pytest_cmd": f"pytest {' '.join(test_files)}" if test_files else None}
    candidates = [s for s in index.symbols if s.name == file_or_symbol]
    if not candidates:
        return {"target": file_or_symbol, "test_files": [], "count": 0}
    sym = candidates[0]
    test_files = index.test_map.get(sym.file_path, [])
    ref_tests = [f for f in index.name_reference_map.get(file_or_symbol, []) if "test" in f.lower()]
    all_tests = list(set(test_files + ref_tests))
    return {"target": file_or_symbol, "source_file": sym.file_path, "test_files": all_tests, "count": len(all_tests), "pytest_cmd": f"pytest {' '.join(all_tests)}" if all_tests else None}


def impact_analysis(root_path, index, symbol_name):
    graph = build_dependency_graph(index)
    candidates = [s for s in index.symbols if s.name == symbol_name or s.qualified_name == symbol_name]
    if not candidates:
        return {"symbol": symbol_name, "found": False}
    sym = candidates[0]
    import_deps = get_dependents(graph, sym.file_path, edge_type="import")
    ref_files = index.name_reference_map.get(symbol_name, [])
    test_files = index.test_map.get(sym.file_path, [])
    call_graph = get_call_graph(root_path, index, symbol_name)
    total_refs = len(set(import_deps + ref_files))
    risk = "high" if total_refs > 10 else ("medium" if total_refs > 3 else "low")
    if not test_files:
        risk = "high" if risk != "high" else risk
    return {"symbol": sym.qualified_name, "file": sym.file_path, "line": sym.line_start, "import_dependents": import_deps, "reference_files": ref_files, "test_files": test_files, "call_graph": call_graph.get("calls", []), "total_impact_files": total_refs, "risk": risk}


def get_file_summary(index, root_path, file_path):
    summary = _get_file_summary(index, root_path, file_path)
    if summary is None:
        return {"path": file_path, "found": False}
    return summary.model_dump()


def search_summaries(index, root_path, query):
    results = _search_summaries(index, root_path, query)
    return {"query": query, "results": results, "count": len(results)}


def get_directory_summary(index, root_path, dir_path):
    summary = _get_dir_summary(index, root_path, dir_path)
    return summary.model_dump()


def resolve_symbol(name, index, graph, context_file=None, context_position=None, expected_kind=None, lsp=None):
    """Import-aware, context-aware symbol resolver with 5-phase resolution."""
    candidates = [s for s in index.symbols if s.name == name]
    if not candidates:
        partial = [s for s in index.symbols if name.lower() in s.name.lower()]
        candidates = partial[:5] if partial else []
        if not candidates:
            return DisambiguatedResult(symbol=name, resolution_method="not_found")

    if context_file:
        file_imports = [i for i in index.imports if i.file_path == context_file]
        for imp in file_imports:
            if imp.imported_name == name and imp.module:
                exact = _find_in_module(candidates, imp.module, name)
                if exact:
                    return DisambiguatedResult(symbol=name, candidates=[_to_candidate(exact, 1.0, "Direct import from context file")], disambiguation_needed=False, resolution_method="import_context")
            if imp.alias == name and imp.imported_name:
                exact = _find_in_module(candidates, imp.module, imp.imported_name)
                if exact:
                    return DisambiguatedResult(symbol=name, candidates=[_to_candidate(exact, 1.0, "Aliased import")], disambiguation_needed=False, resolution_method="import_context")
        local = [c for c in candidates if c.file_path == context_file]
        if len(local) == 1:
            return DisambiguatedResult(symbol=name, candidates=[_to_candidate(local[0], 0.95, "Local definition in context file")], disambiguation_needed=False, resolution_method="local_definition")

    if lsp and lsp.is_running and context_file and context_position:
        root = index.root_path
        abs_path = str(Path(root) / context_file)
        result = lsp.go_to_definition(abs_path, context_position[0], context_position[1])
        if result:
            for loc in result:
                for c in candidates:
                    candidate_abs = str(Path(root) / c.file_path)
                    if candidate_abs == loc.get("file", "") and abs(c.line_start - 1 - loc.get("line", 0)) <= 1:
                        return DisambiguatedResult(symbol=name, candidates=[_to_candidate(c, 1.0, "LSP resolved")], disambiguation_needed=False, resolution_method="lsp")

    scored = _rank_candidates(candidates, context_file, graph, expected_kind)
    disambiguation_needed = len(scored) >= 2 and scored[0].confidence - scored[1].confidence < 0.15
    return DisambiguatedResult(symbol=name, candidates=scored, disambiguation_needed=disambiguation_needed, resolution_method="ranked_fallback")


def _find_in_module(candidates, module, name):
    if not module:
        return None
    module_path = module.replace(".", "/")
    for c in candidates:
        if c.name == name and module_path in c.file_path:
            return c
    return None


def _to_candidate(sym, confidence, reason):
    return SymbolCandidate(qualified_name=sym.qualified_name, kind=sym.kind, file_path=sym.file_path, line=sym.line_start, signature=sym.signature, confidence=confidence, reason=reason)


def _rank_candidates(candidates, context_file, graph, expected_kind):
    scored = []
    for c in candidates:
        score = 0.0
        reasons = []
        if context_file:
            if c.file_path == context_file:
                score += 0.45; reasons.append("Same file as context")
            else:
                ctx_parts = context_file.split("/"); c_parts = c.file_path.split("/")
                if len(ctx_parts) > 1 and len(c_parts) > 1 and ctx_parts[0] == c_parts[0]:
                    score += 0.25; reasons.append("Same package")
            if context_file in graph and c.file_path in graph:
                try:
                    path_len = nx.shortest_path_length(graph, context_file, c.file_path)
                    if path_len == 1: score += 0.15; reasons.append("Direct dependency")
                    elif path_len == 2: score += 0.08; reasons.append("Indirect dependency")
                except nx.NetworkXNoPath:
                    pass
        if "test" not in c.file_path.lower():
            score += 0.10; reasons.append("Production source")
        if expected_kind and c.kind == expected_kind:
            score += 0.10; reasons.append(f"Matches expected kind: {expected_kind}")
        if c.docstring:
            score += 0.02; reasons.append("Documented")
        max_possible = 0.45 + 0.25 + 0.15 + 0.10 + 0.10 + 0.02
        normalized = min(score / max_possible, 1.0) if max_possible > 0 else 0.0
        scored.append(SymbolCandidate(qualified_name=c.qualified_name, kind=c.kind, file_path=c.file_path, line=c.line_start, signature=c.signature, confidence=normalized, reason="; ".join(reasons)))
    scored.sort(key=lambda x: -x.confidence)
    return scored


def _read_lines(root_path, file_path, start, end):
    abs_path = Path(root_path) / file_path
    try:
        lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[max(0, start - 1):end])
    except OSError:
        return ""
