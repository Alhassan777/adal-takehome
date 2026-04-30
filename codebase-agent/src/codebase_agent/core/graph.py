"""Multi-edge dependency graph using networkx MultiDiGraph."""

from collections import defaultdict

import networkx as nx

from ..models import RepoIndex


def build_dependency_graph(index: RepoIndex) -> nx.MultiDiGraph:
    """Build a graph with import, test, and reference edges."""
    G = nx.MultiDiGraph()

    for f in index.files:
        G.add_node(f.path)

    # Import edges
    for imp in index.imports:
        if imp.module:
            target = _resolve_import_to_file(imp.module, index)
            if target and target != imp.file_path:
                G.add_edge(imp.file_path, target, type="import", module=imp.module)

    # Test edges
    for source_file, test_files in index.test_map.items():
        for test_file in test_files:
            G.add_edge(test_file, source_file, type="test")

    # Reference edges (coarse, name-based)
    for symbol_name, ref_files in index.name_reference_map.items():
        for ref_file in ref_files:
            symbols_in_file = [
                s for s in index.symbols
                if s.name == symbol_name and s.file_path != ref_file
            ]
            for sym in symbols_in_file:
                G.add_edge(ref_file, sym.file_path, type="reference", symbol=symbol_name)

    return G


def get_dependencies(
    graph: nx.MultiDiGraph,
    file_path: str,
    edge_type: str | None = None,
) -> list[str]:
    """Get forward dependencies (files this file depends on)."""
    if file_path not in graph:
        return []
    deps = set()
    for _, target, data in graph.out_edges(file_path, data=True):
        if edge_type is None or data.get("type") == edge_type:
            deps.add(target)
    return sorted(deps)


def get_dependents(
    graph: nx.MultiDiGraph,
    file_path: str,
    edge_type: str | None = None,
) -> list[str]:
    """Get reverse dependencies (files that depend on this file)."""
    if file_path not in graph:
        return []
    deps = set()
    for source, _, data in graph.in_edges(file_path, data=True):
        if edge_type is None or data.get("type") == edge_type:
            deps.add(source)
    return sorted(deps)


def get_test_files(graph: nx.MultiDiGraph, file_path: str) -> list[str]:
    """Get test files that cover a given source file."""
    return get_dependents(graph, file_path, edge_type="test")


def get_files_referencing(graph: nx.MultiDiGraph, symbol_name: str) -> list[str]:
    """Get files that reference a symbol (from name_reference_map edges)."""
    files = set()
    for u, v, data in graph.edges(data=True):
        if data.get("type") == "reference" and data.get("symbol") == symbol_name:
            files.add(u)
    return sorted(files)


def get_transitive_dependents(
    graph: nx.MultiDiGraph,
    file_path: str,
    max_depth: int = 3,
    edge_types: set[str] | None = None,
) -> list[str]:
    """BFS for transitive reverse dependencies with depth limit."""
    if file_path not in graph:
        return []

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(file_path, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for source, _, data in graph.in_edges(current, data=True):
            if edge_types and data.get("type") not in edge_types:
                continue
            if source not in visited:
                visited.add(source)
                queue.append((source, depth + 1))

    visited.discard(file_path)
    return sorted(visited)


def _resolve_import_to_file(module: str, index: RepoIndex) -> str | None:
    """Resolve a module name to a file path in the index."""
    candidate = module.replace(".", "/") + ".py"
    for f in index.files:
        if f.path == candidate or f.path.endswith("/" + candidate):
            return f.path
    pkg_init = module.replace(".", "/") + "/__init__.py"
    for f in index.files:
        if f.path == pkg_init or f.path.endswith("/" + pkg_init):
            return f.path
    return None
