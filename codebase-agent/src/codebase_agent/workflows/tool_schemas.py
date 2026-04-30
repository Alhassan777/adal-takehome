"""Auto-generate OpenAI function-calling schemas from the tool registry."""

from __future__ import annotations

from typing import Any


TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_symbols_tool": "Search for symbols (functions, classes, methods) by name pattern across the codebase.",
    "search_text_tool": "Search for a regex pattern in files using ripgrep. Returns matching lines with file paths.",
    "get_definition": "Resolve a symbol to its definition location using LSP or tree-sitter index. Supports disambiguation.",
    "find_references": "Find all references to a symbol across the codebase using LSP or name-reference map.",
    "read_snippet": "Read specific lines from a file. Returns the content between start_line and end_line.",
    "get_imports": "List all imports for a given file with resolved module paths.",
    "trace_module": "Get forward and reverse dependency information for a file (depends_on, depended_by, test_files).",
    "get_call_graph": "Get the outgoing call graph for a function/method (what it calls).",
    "find_tests": "Find test files that cover a given file or symbol.",
    "impact_analysis": "Analyze the impact of changing a symbol: references, dependents, tests, and risk level.",
    "get_file_summary": "Get the NL summary for a file (purpose, responsibilities, side effects, dependencies).",
    "search_summaries": "Keyword search across file summaries to find files relevant to a topic.",
    "get_directory_summary": "Get a summary of a directory (role, contents, common dependencies).",
    "list_tree": "Get a compact directory tree listing of the repository.",
    "repo_map": "Get a hierarchical annotated repository map with roles and key symbols per directory.",
}

TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "search_symbols_tool": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Symbol name or pattern to search for"},
        },
        "required": ["query"],
    },
    "search_text_tool": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Regex pattern to search for"},
            "file_glob": {"type": "string", "description": "File glob to restrict search (default: *.py)", "default": "*.py"},
        },
        "required": ["query"],
    },
    "get_definition": {
        "type": "object",
        "properties": {
            "symbol_name": {"type": "string", "description": "The symbol name to look up"},
            "context_file": {"type": "string", "description": "File where the symbol is used (helps disambiguation)"},
        },
        "required": ["symbol_name"],
    },
    "find_references": {
        "type": "object",
        "properties": {
            "symbol_name": {"type": "string", "description": "Symbol to find all references for"},
        },
        "required": ["symbol_name"],
    },
    "read_snippet": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Relative path to the file"},
            "start_line": {"type": "integer", "description": "First line to read (1-indexed)", "default": 1},
            "end_line": {"type": "integer", "description": "Last line to read", "default": 50},
        },
        "required": ["file_path"],
    },
    "get_imports": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "File to list imports for"},
        },
        "required": ["file_path"],
    },
    "trace_module": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "File to trace dependencies for"},
        },
        "required": ["file_path"],
    },
    "get_call_graph": {
        "type": "object",
        "properties": {
            "symbol_name": {"type": "string", "description": "Function or method to get outgoing calls for"},
        },
        "required": ["symbol_name"],
    },
    "find_tests": {
        "type": "object",
        "properties": {
            "file_or_symbol": {"type": "string", "description": "File path or symbol name to find tests for"},
        },
        "required": ["file_or_symbol"],
    },
    "impact_analysis": {
        "type": "object",
        "properties": {
            "symbol_name": {"type": "string", "description": "Symbol to analyze change impact for"},
        },
        "required": ["symbol_name"],
    },
    "get_file_summary": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "File to get summary for"},
        },
        "required": ["file_path"],
    },
    "search_summaries": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords to search across file summaries"},
        },
        "required": ["query"],
    },
    "get_directory_summary": {
        "type": "object",
        "properties": {
            "dir_path": {"type": "string", "description": "Directory path to summarize"},
        },
        "required": ["dir_path"],
    },
    "list_tree": {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "repo_map": {
        "type": "object",
        "properties": {
            "depth": {"type": "integer", "description": "Max directory depth for the map", "default": 2},
        },
        "required": [],
    },
}


def build_openai_tool_schemas() -> list[dict[str, Any]]:
    """Build the complete list of OpenAI function-calling tool schemas."""
    schemas = []
    for name, description in TOOL_DESCRIPTIONS.items():
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": TOOL_PARAMETERS.get(name, {"type": "object", "properties": {}, "required": []}),
            },
        }
        schemas.append(schema)
    return schemas


def build_tool_signatures_text() -> str:
    """Build a human-readable text block of tool signatures for RLM system prompts."""
    lines = []
    for name, description in TOOL_DESCRIPTIONS.items():
        params = TOOL_PARAMETERS.get(name, {})
        props = params.get("properties", {})
        required = params.get("required", [])
        param_strs = []
        for pname, pinfo in props.items():
            ptype = pinfo.get("type", "any")
            req = "" if pname in required else "=None"
            param_strs.append(f"{pname}: {ptype}{req}")
        sig = f"tools.{name}({', '.join(param_strs)})"
        lines.append(f"{sig}\n    {description}")
    return "\n\n".join(lines)
