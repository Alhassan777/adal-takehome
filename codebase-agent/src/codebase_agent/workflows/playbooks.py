"""Playbook definitions for each workflow type.

Each playbook describes the strategy, required tools, step sequence,
output format, failure chains, and budget for a workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import WorkflowType


@dataclass
class WorkflowPlaybook:
    """A structured set of instructions that guides the agent through a workflow."""

    workflow_type: WorkflowType
    trigger_description: str
    required_tools: list[str]
    strategy_steps: list[str]
    output_format: str
    failure_chains: dict[str, str] = field(default_factory=dict)
    early_termination: str = ""
    max_tool_rounds: int = 4


# --- Tier 1 Playbooks ---

_SYMBOL_LOOKUP = WorkflowPlaybook(
    workflow_type=WorkflowType.SYMBOL_LOOKUP,
    trigger_description="User asks 'where is X defined', 'find X', 'locate X'",
    required_tools=["search_symbols_tool", "get_definition", "read_snippet"],
    strategy_steps=[
        "search_symbols_tool(target) -- find all candidates",
        "If exactly one result: read_snippet at that location",
        "If multiple: use context_file or ask to disambiguate",
        "Return definition with file path and line number",
    ],
    output_format="Symbol name, file path, line number, signature, and code snippet",
    failure_chains={
        "search_symbols_tool returns 0": "search_text_tool with regex: (def|class)\\s+NAME",
        "still nothing": "search_text_tool with just the name as substring",
    },
    early_termination="If exactly one match with high confidence, return immediately",
    max_tool_rounds=3,
)

_FILE_READING = WorkflowPlaybook(
    workflow_type=WorkflowType.FILE_READING,
    trigger_description="User asks to 'show', 'read', or 'display' a specific file",
    required_tools=["read_snippet"],
    strategy_steps=[
        "read_snippet(file_path, start=1, end=large) -- show full file",
    ],
    output_format="Full file content with line numbers",
    failure_chains={"file not found": "list_tree to find similar filenames"},
    early_termination="Always completes in 1 step",
    max_tool_rounds=2,
)

_FILE_LISTING = WorkflowPlaybook(
    workflow_type=WorkflowType.FILE_LISTING,
    trigger_description="User asks 'what files', 'file tree', 'list files'",
    required_tools=["list_tree"],
    strategy_steps=["list_tree(root, depth) -- show directory structure"],
    output_format="Directory tree with file counts",
    failure_chains={},
    early_termination="Always completes in 1 step",
    max_tool_rounds=2,
)

_TEXT_SEARCH = WorkflowPlaybook(
    workflow_type=WorkflowType.TEXT_SEARCH,
    trigger_description="User wants to search/grep for a pattern in the codebase",
    required_tools=["search_text_tool"],
    strategy_steps=[
        "search_text_tool(query, glob) -- find all matches",
        "Return matches with file paths, line numbers, and context",
    ],
    output_format="List of matches with file:line:content format",
    failure_chains={"zero matches": "Try broader glob or looser pattern"},
    early_termination="If matches found, return immediately",
    max_tool_rounds=3,
)

# --- Tier 2 Playbooks ---

_GOTO_DEF_HINT = WorkflowPlaybook(
    workflow_type=WorkflowType.GOTO_DEFINITION_HINT,
    trigger_description="User provides a file + position hint for go-to-definition",
    required_tools=["get_definition", "read_snippet"],
    strategy_steps=[
        "get_definition(symbol, context_file, context_position) -- LSP or index resolve",
        "read_snippet(target_file, definition_lines) -- show the full definition",
        "Return complete definition with source context",
    ],
    output_format="Definition file, line, signature, and full source code",
    failure_chains={
        "LSP fails": "Fall back to tree-sitter index lookup",
        "symbol not found at position": "read_snippet of the file to find it manually",
    },
    early_termination="Once definition is found and shown, done",
    max_tool_rounds=3,
)

_GOTO_DEF_NO_HINT = WorkflowPlaybook(
    workflow_type=WorkflowType.GOTO_DEFINITION_NO_HINT,
    trigger_description="User asks about a symbol used in a known file (no position)",
    required_tools=["read_snippet", "search_symbols_tool", "get_definition"],
    strategy_steps=[
        "read_snippet(context_file) -- find where the symbol appears",
        "Determine the symbol's position from the file content",
        "get_definition(symbol, context_file, position) -- resolve to source",
        "read_snippet(target_file, definition_lines) -- show definition",
    ],
    output_format="Symbol definition with file path, line number, and source code",
    failure_chains={
        "symbol not visible in file": "search_symbols_tool(name) across codebase",
        "get_definition fails": "search_text_tool('def NAME' or 'class NAME')",
    },
    early_termination="Once definition located, stop",
    max_tool_rounds=4,
)

_GOTO_DEF_NO_FILE = WorkflowPlaybook(
    workflow_type=WorkflowType.GOTO_DEFINITION_NO_FILE,
    trigger_description="User asks to find a symbol definition with no file/position context",
    required_tools=["search_symbols_tool", "search_text_tool", "read_snippet"],
    strategy_steps=[
        "search_symbols_tool(name) -- find candidates across the project",
        "If multiple: rank by production files, documented symbols",
        "read_snippet(best_match_file, definition_lines) -- show definition",
    ],
    output_format="Definition location with full source code",
    failure_chains={
        "search_symbols_tool returns 0": "search_text_tool('(def|class)\\s+NAME')",
        "still nothing": "search_text_tool(NAME) for any mention",
    },
    early_termination="If exactly one candidate, show it immediately",
    max_tool_rounds=4,
)

_IMPORT_TRACING = WorkflowPlaybook(
    workflow_type=WorkflowType.IMPORT_TRACING,
    trigger_description="User asks what a file imports / depends on",
    required_tools=["get_imports", "trace_module"],
    strategy_steps=[
        "get_imports(file) -- list all imports with resolved paths",
        "For each import, note the source module path",
        "Return dependency list with module purposes",
    ],
    output_format="List of imports with source file paths and what they provide",
    failure_chains={"file not in index": "read_snippet and parse imports manually"},
    early_termination="Once imports are listed, done",
    max_tool_rounds=3,
)

_REVERSE_IMPORT = WorkflowPlaybook(
    workflow_type=WorkflowType.REVERSE_IMPORT_TRACING,
    trigger_description="User asks who imports/depends on a file",
    required_tools=["trace_module"],
    strategy_steps=[
        "trace_module(file) -- get reverse dependencies",
        "Return all files that import the target",
    ],
    output_format="List of files that depend on the target, with import statements",
    failure_chains={
        "trace_module finds nothing": "search_text_tool('from MODULE import' or 'import MODULE')",
    },
    early_termination="Once dependents listed, done",
    max_tool_rounds=3,
)

# --- Tier 3 Playbooks ---

_FEATURE_EXPLANATION = WorkflowPlaybook(
    workflow_type=WorkflowType.FEATURE_EXPLANATION,
    trigger_description="User asks 'how does X work', 'explain X', 'what does X do'",
    required_tools=[
        "search_summaries", "search_symbols_tool", "get_file_summary",
        "get_definition", "get_imports", "find_tests", "read_snippet",
    ],
    strategy_steps=[
        "search_summaries(feature_keywords) -- find files whose summaries mention the feature",
        "For top 2-3 files: get_file_summary(path) -- understand purpose before reading",
        "search_symbols_tool(feature_name) -- find concrete symbols",
        "get_definition for key symbols -- read implementations",
        "get_imports for those files -- understand data flow and dependencies",
        "find_tests -- see how the feature is exercised",
        "Synthesize: explain the feature flow file-by-file with line references",
    ],
    output_format=(
        "- One-paragraph overview\n"
        "- File-by-file breakdown with paths and key functions\n"
        "- Data flow description\n"
        "- Related test files"
    ),
    failure_chains={
        "search_summaries returns 0": "search_text_tool(feature_keywords) then read_snippet on top matches",
        "search_symbols_tool returns 0": "search_text_tool with broader terms",
        "only 1 file found": "Just explain that file directly (early termination)",
    },
    early_termination="If only 1 file matches and it's small (<50 lines), explain directly",
    max_tool_rounds=8,
)

_IMPACT_ANALYSIS = WorkflowPlaybook(
    workflow_type=WorkflowType.IMPACT_ANALYSIS,
    trigger_description="User asks 'what breaks if I change X', 'what depends on X'",
    required_tools=["get_definition", "find_references", "trace_module", "find_tests", "impact_analysis"],
    strategy_steps=[
        "get_definition(symbol) -- locate the target",
        "find_references(symbol) -- all usage sites",
        "trace_module(file, direction='reverse') -- import dependents",
        "find_tests(symbol) -- test coverage",
        "Assess risk: High (>10 refs or API routes), Medium (3-10, has tests), Low (<3, well-tested)",
    ],
    output_format=(
        "- Definition location\n"
        "- List of affected files with specific line references\n"
        "- Test coverage status\n"
        "- Risk level (High/Medium/Low) with justification"
    ),
    failure_chains={
        "find_references returns 0": "Check name_reference_map via search_text_tool; symbol might be used dynamically",
        "get_definition not found": "search_symbols_tool(name) then retry",
    },
    early_termination="If symbol is only used in its own file + tests, report 'Low risk, locally scoped'",
    max_tool_rounds=6,
)

_TEST_DISCOVERY = WorkflowPlaybook(
    workflow_type=WorkflowType.TEST_DISCOVERY,
    trigger_description="User asks 'what tests cover X', 'how is X tested'",
    required_tools=["find_tests", "search_text_tool"],
    strategy_steps=[
        "find_tests(file_or_symbol) -- check precomputed test_map",
        "If no results: search_text_tool(name, glob='*test*') -- search test files",
        "Return test file paths + suggested pytest command",
    ],
    output_format="Test files covering the target, with pytest command to run them",
    failure_chains={
        "find_tests returns 0": "search_text_tool(symbol_name) restricted to test files",
        "still nothing": "Report 'no tests found' as actionable feedback",
    },
    early_termination="Once test files are identified, done",
    max_tool_rounds=4,
)

_CALL_GRAPH = WorkflowPlaybook(
    workflow_type=WorkflowType.CALL_GRAPH,
    trigger_description="User asks 'what does X call', 'call graph of X'",
    required_tools=["get_call_graph", "get_definition"],
    strategy_steps=[
        "get_definition(symbol) -- ensure it exists and locate it",
        "get_call_graph(symbol, depth=1) -- downstream calls",
        "For unresolved calls: search_symbols_tool to try resolving",
        "Return call tree with resolution status",
    ],
    output_format="Call tree showing: function -> [list of called functions with files]",
    failure_chains={
        "symbol not found": "search_symbols_tool(name) to locate",
        "call graph empty": "read_snippet of the function, report its body directly",
    },
    early_termination="Once call graph is built, done",
    max_tool_rounds=5,
)

_REVERSE_CALL_GRAPH = WorkflowPlaybook(
    workflow_type=WorkflowType.REVERSE_CALL_GRAPH,
    trigger_description="User asks 'what calls X', 'callers of X'",
    required_tools=["find_references", "get_definition"],
    strategy_steps=[
        "find_references(symbol) -- all usage sites",
        "Filter to call sites (lines containing 'symbol(')",
        "For each caller: identify the enclosing function",
        "Return callers with context",
    ],
    output_format="List of functions that call the target, with file paths and line numbers",
    failure_chains={
        "find_references returns 0": "search_text_tool(NAME + '(') to find call sites",
    },
    early_termination="Once callers are identified, done",
    max_tool_rounds=5,
)

# --- Tier 4 Playbooks ---

_MODULE_OVERVIEW = WorkflowPlaybook(
    workflow_type=WorkflowType.MODULE_OVERVIEW,
    trigger_description="User asks to explain a directory/package/module",
    required_tools=["get_directory_summary", "list_tree", "get_file_summary", "search_symbols_tool"],
    strategy_steps=[
        "get_directory_summary(path) -- high-level module summary",
        "list_tree(path) -- see all files in the module",
        "For key files: get_file_summary -- understand each file's role",
        "Identify patterns (shared base classes, common imports)",
        "Explain module responsibilities and interactions",
    ],
    output_format=(
        "- Module purpose (1 sentence)\n"
        "- File-by-file roles\n"
        "- Key symbols and their relationships\n"
        "- How this module connects to the rest of the codebase"
    ),
    failure_chains={
        "directory not found": "list_tree at root to find the correct path",
        "no summaries cached": "read_snippet on each file to understand manually",
    },
    early_termination="If directory has only 1-2 files, explain directly",
    max_tool_rounds=6,
)

_ARCHITECTURE_MAP = WorkflowPlaybook(
    workflow_type=WorkflowType.ARCHITECTURE_MAP,
    trigger_description="User asks about high-level architecture/structure",
    required_tools=["repo_map", "get_directory_summary", "trace_module"],
    strategy_steps=[
        "repo_map(depth=2) -- get hierarchical overview with roles",
        "Identify layers from directory roles (routes/services/models/utils)",
        "For key directories: get_directory_summary -- understand purpose",
        "trace_module for a few central files -- understand connections",
        "Synthesize layered architecture explanation",
    ],
    output_format=(
        "- Project type and framework\n"
        "- Layer-by-layer breakdown\n"
        "- Key data flows between layers\n"
        "- Entry points (routes, CLI, main)"
    ),
    failure_chains={
        "repo_map too large": "Focus on top-level directories only (depth=1)",
    },
    early_termination="If project is small (<10 files), just list everything",
    max_tool_rounds=6,
)

_API_SURFACE = WorkflowPlaybook(
    workflow_type=WorkflowType.API_SURFACE,
    trigger_description="User asks about public API/interface of a module",
    required_tools=["search_symbols_tool", "get_file_summary", "read_snippet"],
    strategy_steps=[
        "search_symbols_tool in the target file/module",
        "Filter to public symbols (no underscore prefix)",
        "Get signatures and docstrings for each",
        "Return structured API surface",
    ],
    output_format="List of public functions/classes with signatures, docstrings, and types",
    failure_chains={"file not found": "list_tree to locate the module"},
    early_termination="Once symbols are listed with signatures, done",
    max_tool_rounds=4,
)

_DEPENDENCY_GRAPH = WorkflowPlaybook(
    workflow_type=WorkflowType.DEPENDENCY_GRAPH,
    trigger_description="User asks for the full dependency/import graph",
    required_tools=["trace_module", "repo_map"],
    strategy_steps=[
        "repo_map(depth=1) -- identify all modules",
        "trace_module for each key module -- build adjacency list",
        "Identify cycles, leaf modules, hub modules",
        "Return graph description",
    ],
    output_format="Module dependency graph showing imports between top-level packages",
    failure_chains={},
    early_termination="Once graph is mapped, done",
    max_tool_rounds=6,
)

# --- Tier 5 Playbooks ---

_SAFE_REFACTORING = WorkflowPlaybook(
    workflow_type=WorkflowType.SAFE_REFACTORING,
    trigger_description="User asks 'can I safely rename/refactor X'",
    required_tools=["find_references", "find_tests", "search_text_tool"],
    strategy_steps=[
        "find_references(symbol) -- all usage sites",
        "find_tests(symbol) -- verify test coverage",
        "search_text_tool('\"symbol_name\"' or \"'symbol_name'\") -- check dynamic/string references",
        "Assess: scope of change, test coverage, dynamic usage risk",
        "Return refactoring scope + risk assessment",
    ],
    output_format=(
        "- All files that need updating\n"
        "- Lines that reference the symbol\n"
        "- Dynamic/string references (higher risk)\n"
        "- Test coverage for affected code\n"
        "- Risk verdict: Safe / Caution / Risky"
    ),
    failure_chains={
        "find_references returns 0": "Symbol may be unused (dead code) -- report as safe to rename",
    },
    early_termination="If 0 references outside definition, safe to rename",
    max_tool_rounds=5,
)

_DEAD_CODE = WorkflowPlaybook(
    workflow_type=WorkflowType.DEAD_CODE,
    trigger_description="User asks 'is X still used', 'dead code', 'unused'",
    required_tools=["find_references", "trace_module", "search_text_tool"],
    strategy_steps=[
        "find_references(symbol) -- check for any usages",
        "If references exist: check if they're reachable from entry points",
        "search_text_tool for string-based references",
        "Return verdict: used/unused with evidence",
    ],
    output_format="Verdict (used/unused) with evidence: reference count, referencing files, reachability",
    failure_chains={
        "find_references returns 0": "Likely dead code; confirm with search_text_tool",
    },
    early_termination="If zero references anywhere, report as dead code immediately",
    max_tool_rounds=4,
)

_MISSING_TESTS = WorkflowPlaybook(
    workflow_type=WorkflowType.MISSING_TESTS,
    trigger_description="User asks about untested functions or coverage gaps",
    required_tools=["search_symbols_tool", "find_tests"],
    strategy_steps=[
        "search_symbols_tool('') -- get all functions/classes in source files",
        "For each symbol: find_tests(symbol) -- check coverage",
        "Collect symbols with zero test coverage",
        "Return untested functions with file paths",
    ],
    output_format="List of untested functions/classes with file paths and suggested test commands",
    failure_chains={},
    early_termination="If all functions are tested, report full coverage",
    max_tool_rounds=6,
)

_BREAKING_CHANGE = WorkflowPlaybook(
    workflow_type=WorkflowType.BREAKING_CHANGE,
    trigger_description="User asks 'what if I remove field/method X from Y'",
    required_tools=["get_definition", "find_references", "search_text_tool", "find_tests"],
    strategy_steps=[
        "get_definition(parent_symbol) -- find the class/module",
        "find_references(field_name) scoped to usages of parent",
        "search_text_tool(field_name) -- catch dynamic access patterns",
        "find_tests -- identify tests that would break",
        "Return full impact assessment",
    ],
    output_format=(
        "- All usages of the field/method\n"
        "- Files that would break\n"
        "- Tests that would fail\n"
        "- Migration steps needed"
    ),
    failure_chains={
        "field_name too common": "Scope search to files that import the parent class",
    },
    early_termination="If field is only used in its definition and tests, low impact",
    max_tool_rounds=6,
)

# --- Tier 6 Playbooks ---

_FOLLOW_UP = WorkflowPlaybook(
    workflow_type=WorkflowType.FOLLOW_UP,
    trigger_description="User asks a follow-up question referencing prior context",
    required_tools=["read_snippet", "get_definition", "search_symbols_tool"],
    strategy_steps=[
        "Resolve references from prior context (file names, symbols mentioned)",
        "Execute the appropriate action based on what they're asking about",
        "Return detailed information about the referenced item",
    ],
    output_format="Detailed explanation of the referenced item from prior context",
    failure_chains={
        "can't resolve reference": "Ask for clarification about which item they mean",
    },
    early_termination="Once the referenced item is explained, done",
    max_tool_rounds=4,
)

_COMPARISON = WorkflowPlaybook(
    workflow_type=WorkflowType.COMPARISON,
    trigger_description="User asks to compare two symbols/implementations",
    required_tools=["get_definition", "read_snippet", "get_imports"],
    strategy_steps=[
        "get_definition(symbol_a) -- find first symbol",
        "get_definition(symbol_b) -- find second symbol",
        "read_snippet for both -- get full implementations",
        "Compare: signatures, bodies, dependencies, callers",
        "Highlight differences and similarities",
    ],
    output_format=(
        "- Side-by-side comparison of signatures\n"
        "- Key differences in implementation\n"
        "- Shared vs unique dependencies\n"
        "- When to use which"
    ),
    failure_chains={
        "one symbol not found": "search_symbols_tool with partial name",
    },
    early_termination="Once both are shown with comparison, done",
    max_tool_rounds=5,
)

_EXPLICIT_CONTEXT = WorkflowPlaybook(
    workflow_type=WorkflowType.EXPLICIT_CONTEXT,
    trigger_description="User @-mentions a file and asks to explain it",
    required_tools=["get_file_summary", "search_symbols_tool", "read_snippet"],
    strategy_steps=[
        "get_file_summary(mentioned_file) -- structured overview",
        "search_symbols_tool in that file -- find key symbols",
        "read_snippet for top symbols -- understand implementations",
        "Explain the file's responsibilities, key functions, and how it connects",
    ],
    output_format=(
        "- File purpose (1 sentence)\n"
        "- Key symbols with brief explanations\n"
        "- Dependencies and dependents\n"
        "- Role in the broader architecture"
    ),
    failure_chains={
        "file not in index": "read_snippet the raw file and explain from content",
    },
    early_termination="Once file is explained with key symbols, done",
    max_tool_rounds=5,
)


# --- Registry ---

PLAYBOOKS: dict[WorkflowType, WorkflowPlaybook] = {
    WorkflowType.SYMBOL_LOOKUP: _SYMBOL_LOOKUP,
    WorkflowType.FILE_READING: _FILE_READING,
    WorkflowType.FILE_LISTING: _FILE_LISTING,
    WorkflowType.TEXT_SEARCH: _TEXT_SEARCH,
    WorkflowType.GOTO_DEFINITION_HINT: _GOTO_DEF_HINT,
    WorkflowType.GOTO_DEFINITION_NO_HINT: _GOTO_DEF_NO_HINT,
    WorkflowType.GOTO_DEFINITION_NO_FILE: _GOTO_DEF_NO_FILE,
    WorkflowType.IMPORT_TRACING: _IMPORT_TRACING,
    WorkflowType.REVERSE_IMPORT_TRACING: _REVERSE_IMPORT,
    WorkflowType.FEATURE_EXPLANATION: _FEATURE_EXPLANATION,
    WorkflowType.IMPACT_ANALYSIS: _IMPACT_ANALYSIS,
    WorkflowType.TEST_DISCOVERY: _TEST_DISCOVERY,
    WorkflowType.CALL_GRAPH: _CALL_GRAPH,
    WorkflowType.REVERSE_CALL_GRAPH: _REVERSE_CALL_GRAPH,
    WorkflowType.MODULE_OVERVIEW: _MODULE_OVERVIEW,
    WorkflowType.ARCHITECTURE_MAP: _ARCHITECTURE_MAP,
    WorkflowType.API_SURFACE: _API_SURFACE,
    WorkflowType.DEPENDENCY_GRAPH: _DEPENDENCY_GRAPH,
    WorkflowType.SAFE_REFACTORING: _SAFE_REFACTORING,
    WorkflowType.DEAD_CODE: _DEAD_CODE,
    WorkflowType.MISSING_TESTS: _MISSING_TESTS,
    WorkflowType.BREAKING_CHANGE: _BREAKING_CHANGE,
    WorkflowType.FOLLOW_UP: _FOLLOW_UP,
    WorkflowType.COMPARISON: _COMPARISON,
    WorkflowType.EXPLICIT_CONTEXT: _EXPLICIT_CONTEXT,
}


def get_playbook(workflow_type: WorkflowType) -> WorkflowPlaybook:
    """Get the playbook for a workflow type."""
    return PLAYBOOKS[workflow_type]
