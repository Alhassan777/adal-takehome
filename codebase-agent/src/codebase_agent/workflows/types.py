"""Workflow type definitions -- all supported agent navigation workflows."""

from enum import Enum


class WorkflowType(str, Enum):
    """All supported agent workflow types, organized by tier."""

    # Tier 1: Direct Lookup (1-2 tool calls)
    SYMBOL_LOOKUP = "symbol_lookup"
    FILE_READING = "file_reading"
    FILE_LISTING = "file_listing"
    TEXT_SEARCH = "text_search"

    # Tier 2: Navigational (2-4 tool calls)
    GOTO_DEFINITION_HINT = "goto_definition_hint"
    GOTO_DEFINITION_NO_HINT = "goto_definition_no_hint"
    GOTO_DEFINITION_NO_FILE = "goto_definition_no_file"
    IMPORT_TRACING = "import_tracing"
    REVERSE_IMPORT_TRACING = "reverse_import_tracing"

    # Tier 3: Analytical (4-8 tool calls)
    FEATURE_EXPLANATION = "feature_explanation"
    IMPACT_ANALYSIS = "impact_analysis"
    TEST_DISCOVERY = "test_discovery"
    CALL_GRAPH = "call_graph"
    REVERSE_CALL_GRAPH = "reverse_call_graph"

    # Tier 4: Structural Understanding
    MODULE_OVERVIEW = "module_overview"
    ARCHITECTURE_MAP = "architecture_map"
    API_SURFACE = "api_surface"
    DEPENDENCY_GRAPH = "dependency_graph"

    # Tier 5: Change-Oriented
    SAFE_REFACTORING = "safe_refactoring"
    DEAD_CODE = "dead_code"
    MISSING_TESTS = "missing_tests"
    BREAKING_CHANGE = "breaking_change"

    # Tier 6: Contextual/Conversational
    FOLLOW_UP = "follow_up"
    COMPARISON = "comparison"
    EXPLICIT_CONTEXT = "explicit_context"


TIER_MAP: dict[WorkflowType, int] = {
    WorkflowType.SYMBOL_LOOKUP: 1,
    WorkflowType.FILE_READING: 1,
    WorkflowType.FILE_LISTING: 1,
    WorkflowType.TEXT_SEARCH: 1,
    WorkflowType.GOTO_DEFINITION_HINT: 2,
    WorkflowType.GOTO_DEFINITION_NO_HINT: 2,
    WorkflowType.GOTO_DEFINITION_NO_FILE: 2,
    WorkflowType.IMPORT_TRACING: 2,
    WorkflowType.REVERSE_IMPORT_TRACING: 2,
    WorkflowType.FEATURE_EXPLANATION: 3,
    WorkflowType.IMPACT_ANALYSIS: 3,
    WorkflowType.TEST_DISCOVERY: 3,
    WorkflowType.CALL_GRAPH: 3,
    WorkflowType.REVERSE_CALL_GRAPH: 3,
    WorkflowType.MODULE_OVERVIEW: 4,
    WorkflowType.ARCHITECTURE_MAP: 4,
    WorkflowType.API_SURFACE: 4,
    WorkflowType.DEPENDENCY_GRAPH: 4,
    WorkflowType.SAFE_REFACTORING: 5,
    WorkflowType.DEAD_CODE: 5,
    WorkflowType.MISSING_TESTS: 5,
    WorkflowType.BREAKING_CHANGE: 5,
    WorkflowType.FOLLOW_UP: 6,
    WorkflowType.COMPARISON: 6,
    WorkflowType.EXPLICIT_CONTEXT: 6,
}
