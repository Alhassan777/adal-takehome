"""Tree-sitter based Python parser for symbol, import, and reference extraction."""

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node

from ..models import ImportRecord, ParseResult, SymbolRecord

PY_LANGUAGE = Language(tspython.language())

_parser: Parser | None = None


def _get_parser() -> Parser:
    global _parser
    if _parser is None:
        _parser = Parser(PY_LANGUAGE)
    return _parser


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_docstring(body_node: Node, source: bytes) -> str | None:
    """Extract docstring from the first statement of a function/class body."""
    if body_node is None or body_node.type != "block":
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            expr = child.children[0] if child.children else None
            if expr and expr.type == "string":
                raw = _node_text(expr, source)
                return raw.strip("\"'").strip()
        elif child.type != "comment":
            break
    return None


def _extract_signature(node: Node, source: bytes) -> str:
    """Extract the function/method signature (from 'def' to the colon)."""
    line_start = node.start_byte
    colon_pos = source.find(b":", line_start)
    if colon_pos == -1:
        return _node_text(node, source).split("\n")[0]
    return source[line_start:colon_pos].decode("utf-8", errors="replace").strip()


def _get_decorators(node: Node, source: bytes) -> list[str]:
    """Get decorators for a function or class node."""
    decorators = []
    if node.parent and node.parent.type == "decorated_definition":
        for child in node.parent.children:
            if child.type == "decorator":
                decorators.append(_node_text(child, source).strip())
    return decorators


def parse_file(file_path: str, language: str = "python") -> ParseResult:
    """Parse a Python file and extract symbols, imports, and identifier references."""
    path = Path(file_path)
    try:
        source = path.read_bytes()
    except (OSError, IOError):
        return ParseResult()

    parser = _get_parser()
    tree = parser.parse(source)
    root = tree.root_node

    symbols = _extract_symbols(root, source, str(file_path))
    imports = _extract_imports(root, source, str(file_path))
    identifier_refs = _extract_identifier_refs(root, source)

    return ParseResult(
        symbols=symbols,
        imports=imports,
        identifier_refs=identifier_refs,
    )


def _extract_symbols(root: Node, source: bytes, file_path: str) -> list[SymbolRecord]:
    """Extract all class, function, and method definitions."""
    symbols: list[SymbolRecord] = []
    _walk_for_symbols(root, source, file_path, parent_class=None, symbols=symbols)
    return symbols


def _walk_for_symbols(
    node: Node,
    source: bytes,
    file_path: str,
    parent_class: str | None,
    symbols: list[SymbolRecord],
) -> None:
    """Recursively walk the tree to find class and function definitions."""
    for child in node.children:
        target = child
        if child.type == "decorated_definition":
            for sub in child.children:
                if sub.type in ("function_definition", "class_definition"):
                    target = sub
                    break

        if target.type == "function_definition":
            name_node = target.child_by_field_name("name")
            if name_node is None:
                continue
            name = _node_text(name_node, source)
            body = target.child_by_field_name("body")

            is_async = False
            if child.type == "decorated_definition":
                for sib in child.children:
                    if sib.type == "function_definition" and sib == target:
                        break
            prev = target.prev_named_sibling
            if target.parent and any(
                c.type == "async" or (c.type is not None and _node_text(c, source) == "async")
                for c in (target.parent.children if target.parent else [])
                if c.end_byte <= target.start_byte
            ):
                is_async = True

            if parent_class:
                kind = "async_method" if is_async else "method"
                qualified = f"{parent_class}.{name}"
            else:
                kind = "async_function" if is_async else "function"
                qualified = name

            symbols.append(
                SymbolRecord(
                    name=name,
                    qualified_name=qualified,
                    kind=kind,
                    file_path=file_path,
                    line_start=target.start_point[0] + 1,
                    line_end=target.end_point[0] + 1,
                    signature=_extract_signature(target, source),
                    docstring=_extract_docstring(body, source),
                    parent=parent_class,
                )
            )

        elif target.type == "class_definition":
            name_node = target.child_by_field_name("name")
            if name_node is None:
                continue
            class_name = _node_text(name_node, source)
            body = target.child_by_field_name("body")

            symbols.append(
                SymbolRecord(
                    name=class_name,
                    qualified_name=class_name,
                    kind="class",
                    file_path=file_path,
                    line_start=target.start_point[0] + 1,
                    line_end=target.end_point[0] + 1,
                    signature=_extract_signature(target, source),
                    docstring=_extract_docstring(body, source),
                    parent=parent_class,
                )
            )

            if body:
                _walk_for_symbols(body, source, file_path, parent_class=class_name, symbols=symbols)

        else:
            _walk_for_symbols(child, source, file_path, parent_class=parent_class, symbols=symbols)


def _extract_imports(root: Node, source: bytes, file_path: str) -> list[ImportRecord]:
    """Extract all import statements."""
    imports: list[ImportRecord] = []
    _walk_for_imports(root, source, file_path, imports)
    return imports


def _walk_for_imports(node: Node, source: bytes, file_path: str, imports: list[ImportRecord]) -> None:
    for child in node.children:
        if child.type == "import_statement":
            name_node = child.child_by_field_name("name")
            if name_node:
                module_name = _node_text(name_node, source)
                alias_node = child.child_by_field_name("alias")
                alias = _node_text(alias_node, source) if alias_node else None
                imports.append(
                    ImportRecord(
                        file_path=file_path,
                        module=module_name,
                        alias=alias,
                    )
                )

        elif child.type == "import_from_statement":
            module_node = child.child_by_field_name("module_name")
            module = _node_text(module_node, source) if module_node else None

            level = 0
            for dot in child.children:
                if _node_text(dot, source) == ".":
                    level += 1
                elif dot.type == "relative_import":
                    level = _node_text(dot, source).count(".")

            is_relative = level > 0

            for sub in child.children:
                if sub.type == "dotted_name" and sub != module_node:
                    imported_name = _node_text(sub, source)
                    imports.append(
                        ImportRecord(
                            file_path=file_path,
                            module=module,
                            imported_name=imported_name,
                            is_relative=is_relative,
                            level=level,
                        )
                    )
                elif sub.type == "aliased_import":
                    name_part = sub.child_by_field_name("name")
                    alias_part = sub.child_by_field_name("alias")
                    if name_part:
                        imports.append(
                            ImportRecord(
                                file_path=file_path,
                                module=module,
                                imported_name=_node_text(name_part, source),
                                alias=_node_text(alias_part, source) if alias_part else None,
                                is_relative=is_relative,
                                level=level,
                            )
                        )

        elif child.child_count > 0:
            _walk_for_imports(child, source, file_path, imports)


def _extract_identifier_refs(root: Node, source: bytes) -> list[str]:
    """Extract all identifier names for the coarse name_reference_map.

    Skips definition sites (function names, class names, import names).
    Returns deduplicated list of identifier names found in this file.
    """
    SKIP_PARENT_TYPES = {
        "function_definition",
        "class_definition",
        "import_from_statement",
        "import_statement",
    }
    SKIP_FIELD_NAMES = {"name", "module_name"}

    PYTHON_BUILTINS = {
        "True", "False", "None", "print", "len", "range", "str", "int",
        "float", "bool", "list", "dict", "set", "tuple", "type", "super",
        "isinstance", "issubclass", "hasattr", "getattr", "setattr",
        "property", "staticmethod", "classmethod", "object", "Exception",
        "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
        "RuntimeError", "StopIteration", "NotImplementedError", "OSError",
        "IOError", "FileNotFoundError", "ImportError", "ModuleNotFoundError",
    }

    refs: set[str] = set()
    _walk_for_identifiers(root, source, refs, SKIP_PARENT_TYPES, SKIP_FIELD_NAMES, PYTHON_BUILTINS)
    return sorted(refs)


def _walk_for_identifiers(
    node: Node,
    source: bytes,
    refs: set[str],
    skip_parent_types: set[str],
    skip_field_names: set[str],
    builtins: set[str],
) -> None:
    if node.type == "identifier":
        parent = node.parent
        if parent and parent.type in skip_parent_types:
            field_name = None
            for i, child in enumerate(parent.children):
                if child.id == node.id:
                    if parent.type in ("function_definition", "class_definition"):
                        name_child = parent.child_by_field_name("name")
                        if name_child and name_child.id == node.id:
                            return
                    break

        name = _node_text(node, source)
        if name and name not in builtins and not name.startswith("_"):
            refs.add(name)
    else:
        for child in node.children:
            _walk_for_identifiers(child, source, refs, skip_parent_types, skip_field_names, builtins)
