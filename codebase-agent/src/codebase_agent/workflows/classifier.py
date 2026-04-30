"""Two-stage workflow classifier: pattern matching first, LLM fallback second."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import WorkflowType


@dataclass
class ClassificationResult:
    """Result of classifying a user question into a workflow type."""

    workflow: WorkflowType
    confidence: float
    method: str  # "pattern", "llm", "default"
    extracted_params: dict = field(default_factory=dict)


# Stage 1: Deterministic pattern matching
# Each pattern list is tried in order; first match wins within a workflow type.
# Patterns are case-insensitive.
WORKFLOW_PATTERNS: dict[WorkflowType, list[str]] = {
    # Tier 2 (checked before Tier 1 because they're more specific)
    WorkflowType.GOTO_DEFINITION_HINT: [
        r"at line (\d+).*?char(?:acter)?\s*(\d+)",
        r"position\s*(\d+)\s*[,:]\s*(\d+)",
        r"line\s+(\d+)\s+.*?column\s+(\d+)",
    ],
    WorkflowType.IMPORT_TRACING: [
        r"what does (.+?) import",
        r"imports? (?:of|for|in) (.+)",
        r"show (?:me )?(?:the )?imports",
        r"dependencies (?:of|for) (.+)",
    ],
    WorkflowType.REVERSE_IMPORT_TRACING: [
        r"who imports (.+)",
        r"what (?:files? )?imports? (.+)",
        r"dependents? (?:of|for) (.+)",
        r"what depends on (.+)",
    ],

    # Tier 4 (checked before Tier 3 feature_explanation to catch directory/module patterns)
    WorkflowType.ARCHITECTURE_MAP: [
        r"(?:high[- ]level|overall|project) (?:architecture|structure|layout|overview)",
        r"how is (?:the )?(?:project|codebase|repo) (?:organized|structured|laid out)",
        r"architecture (?:of|for)",
        r"give me (?:a|an|the) (?:overview|map|summary)",
    ],
    WorkflowType.MODULE_OVERVIEW: [
        r"explain (?:the )?(.+?)(?:/|\\| directory| folder| package| module)$",
        r"what(?:'s| is) in (?:the )?(.+?)(?:/|\\| directory| folder)$",
        r"overview of (?:the )?(.+?)(?:/|\\| directory| folder| package)?$",
    ],

    # Tier 3
    WorkflowType.IMPACT_ANALYSIS: [
        r"what (?:would )?breaks? if",
        r"impact (?:of|if)",
        r"is it safe to (?:change|rename|remove|delete|modify)",
        r"what (?:is )?affected (?:by|if)",
        r"risk (?:of|if) (?:chang|modif|remov)",
    ],
    WorkflowType.TEST_DISCOVERY: [
        r"what tests? cover",
        r"how is (.+) tested",
        r"find tests? for",
        r"test(?:s|ing)? (?:for|of|covering) (.+)",
        r"pytest.+for",
    ],
    WorkflowType.CALL_GRAPH: [
        r"what does (.+?) call",
        r"call(?:s|ing|ed)? (?:graph|tree|chain) (?:of|for) (.+)",
        r"(.+?) calls what",
    ],
    WorkflowType.REVERSE_CALL_GRAPH: [
        r"what calls (.+)",
        r"who calls (.+)",
        r"callers? (?:of|for) (.+)",
    ],
    WorkflowType.FEATURE_EXPLANATION: [
        r"how does (.+?) work",
        r"explain (?:how )(.+?)(?:\s+works?)?$",
        r"what does (.+?) do",
        r"walk me through (.+)",
        r"describe (?:the )?(.+?)(?:\s+flow|\s+process)?$",
    ],
    WorkflowType.API_SURFACE: [
        r"(?:public )?api (?:of|for|surface) (.+)",
        r"what(?:'s| is) (?:the )?(?:public )?(?:interface|api) (?:of|for) (.+)",
        r"exported (?:symbols?|functions?|classes?) (?:of|from|in) (.+)",
    ],
    WorkflowType.DEPENDENCY_GRAPH: [
        r"dependency graph",
        r"import graph",
        r"module graph",
        r"show (?:me )?(?:the )?(?:full )?depend",
    ],

    # Tier 5
    WorkflowType.SAFE_REFACTORING: [
        r"can i (?:safely )?rename (.+)",
        r"(?:safe|ok) to (?:rename|refactor|move) (.+)",
        r"rename (.+?) to (.+)",
        r"refactor(?:ing)? (.+)",
    ],
    WorkflowType.DEAD_CODE: [
        r"is (.+?) (?:still )?used",
        r"dead code",
        r"unused (?:function|class|method|symbol)",
        r"can i (?:safely )?(?:remove|delete) (.+)",
    ],
    WorkflowType.MISSING_TESTS: [
        r"(?:what|which) (?:functions?|code|symbols?) (?:lack|miss|don't have|without) (?:test|coverage)",
        r"untested (?:functions?|code|symbols?)",
        r"(?:test )?coverage gaps?",
    ],
    WorkflowType.BREAKING_CHANGE: [
        r"what (?:happens?|would happen|breaks?) if i (?:remove|delete|change) (?:the )?(.+?) (?:field|property|attribute|method|param)",
        r"breaking change",
        r"remove (?:the )?(.+?) (?:field|column|property)",
    ],

    # Tier 6
    WorkflowType.COMPARISON: [
        r"(?:how|what) (?:does|is) (.+?) differ(?:s|ent)? from (.+)",
        r"compare (.+?) (?:with|to|and|vs) (.+)",
        r"difference between (.+?) and (.+)",
    ],

    # Tier 1 (checked last -- they're very broad)
    WorkflowType.SYMBOL_LOOKUP: [
        r"where is (.+?) defined",
        r"find where (\w+) is defined",
        r"find (?:the )?definition (?:of )?(.+?)(?:\s|$)",
        r"find (?:the )?(?!where)(\w+)(?:\s|$)",
        r"locate (.+)",
        r"which file (?:defines?|contains?|has) (.+)",
    ],
    WorkflowType.FILE_READING: [
        r"show (?:me )?(.+\.py)",
        r"read (.+\.py)",
        r"(?:display|print|cat) (.+\.py)",
        r"contents? of (.+\.py)",
    ],
    WorkflowType.FILE_LISTING: [
        r"(?:what|which|list) files",
        r"file (?:tree|listing|list|structure)",
        r"ls",
        r"directory (?:listing|structure|tree)",
    ],
    WorkflowType.TEXT_SEARCH: [
        r"(?:search|grep|find|look) for ['\"](.+?)['\"]",
        r"where (?:is|are) ['\"](.+?)['\"]",
        r"(?:search|grep|find) (.+?) in (?:the )?(?:code|codebase|project|files)",
    ],
}


def classify_question(
    question: str,
    mentioned_files: list | None = None,
    conversation_history: list | None = None,
) -> ClassificationResult:
    """Classify a codebase question into a workflow type.

    Uses two stages:
    1. Pattern matching (fast, deterministic)
    2. Keyword heuristics (fallback when no pattern matches)
    """
    # Handle @-mention context: if files are mentioned, it's explicit context
    if mentioned_files and _is_explain_with_mention(question):
        return ClassificationResult(
            workflow=WorkflowType.EXPLICIT_CONTEXT,
            confidence=0.9,
            method="pattern",
            extracted_params={"files": [m.path if hasattr(m, "path") else m for m in mentioned_files]},
        )

    # Handle follow-up questions
    if conversation_history and _is_follow_up(question):
        return ClassificationResult(
            workflow=WorkflowType.FOLLOW_UP,
            confidence=0.8,
            method="pattern",
        )

    # Stage 1: Pattern matching
    q_lower = question.lower().strip()
    for workflow_type, patterns in WORKFLOW_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, q_lower, re.IGNORECASE)
            if match:
                params = extract_params(question, workflow_type, match)
                return ClassificationResult(
                    workflow=workflow_type,
                    confidence=0.85,
                    method="pattern",
                    extracted_params=params,
                )

    # Stage 2: Keyword heuristic fallback
    return _keyword_fallback(q_lower)


def extract_params(
    question: str,
    workflow_type: WorkflowType,
    match: re.Match | None = None,
) -> dict:
    """Extract structured parameters from the matched question."""
    params: dict = {}

    if match and match.groups():
        groups = [g for g in match.groups() if g is not None]
        if workflow_type == WorkflowType.GOTO_DEFINITION_HINT:
            if len(groups) >= 2:
                params["line"] = int(groups[0])
                params["character"] = int(groups[1])
            # Also try to find the symbol name and file
            file_match = re.search(r'in\s+(\S+\.py)', question, re.IGNORECASE)
            if file_match:
                params["file"] = file_match.group(1)
            sym_match = re.search(r'[`\'"]([\w.]+)[`\'"]', question)
            if sym_match:
                params["symbol"] = sym_match.group(1)

        elif workflow_type in (WorkflowType.COMPARISON,):
            if len(groups) >= 2:
                params["symbol_a"] = groups[0].strip("`'\" ?.,!")
                params["symbol_b"] = groups[1].strip("`'\" ?.,!")

        elif workflow_type == WorkflowType.SAFE_REFACTORING:
            if len(groups) >= 2:
                params["old_name"] = groups[0].strip("`'\" ")
                params["new_name"] = groups[1].strip("`'\" ")
            elif len(groups) == 1:
                params["symbol"] = groups[0].strip("`'\" ")

        else:
            # Generic: first captured group is the primary target
            params["target"] = groups[0].strip("`'\" ")

    # Always try to extract quoted/backtick-wrapped symbol names
    if "symbol" not in params and "target" not in params:
        sym_match = re.search(r'[`\'"]([\w.]+)[`\'"]', question)
        if sym_match:
            params["symbol"] = sym_match.group(1)

    # Try to extract file paths
    if "file" not in params:
        file_match = re.search(r'(\S+\.py)\b', question)
        if file_match:
            params["file"] = file_match.group(1)

    return params


def _is_explain_with_mention(question: str) -> bool:
    """Check if the question is about explaining a mentioned file."""
    q = question.lower()
    return any(kw in q for kw in ["explain", "what does", "how does", "describe", "tell me about", "overview"])


def _is_follow_up(question: str) -> bool:
    """Check if this looks like a follow-up question."""
    q = question.lower()
    follow_up_signals = [
        "tell me more",
        "what about",
        "and the",
        "also show",
        "that file",
        "that function",
        "the second",
        "the first",
        "more detail",
        "drill down",
        "go deeper",
        "expand on",
    ]
    return any(signal in q for signal in follow_up_signals)


def _keyword_fallback(question: str) -> ClassificationResult:
    """Keyword-based heuristic when no pattern matches."""
    scores: dict[WorkflowType, float] = {}

    keyword_map: dict[str, tuple[WorkflowType, float]] = {
        "defined": (WorkflowType.SYMBOL_LOOKUP, 0.4),
        "definition": (WorkflowType.SYMBOL_LOOKUP, 0.4),
        "where": (WorkflowType.SYMBOL_LOOKUP, 0.2),
        "find": (WorkflowType.SYMBOL_LOOKUP, 0.2),
        "locate": (WorkflowType.SYMBOL_LOOKUP, 0.3),
        "how": (WorkflowType.FEATURE_EXPLANATION, 0.3),
        "explain": (WorkflowType.FEATURE_EXPLANATION, 0.4),
        "work": (WorkflowType.FEATURE_EXPLANATION, 0.2),
        "flow": (WorkflowType.FEATURE_EXPLANATION, 0.2),
        "impact": (WorkflowType.IMPACT_ANALYSIS, 0.5),
        "break": (WorkflowType.IMPACT_ANALYSIS, 0.4),
        "affect": (WorkflowType.IMPACT_ANALYSIS, 0.4),
        "change": (WorkflowType.IMPACT_ANALYSIS, 0.3),
        "safe": (WorkflowType.SAFE_REFACTORING, 0.3),
        "test": (WorkflowType.TEST_DISCOVERY, 0.4),
        "coverage": (WorkflowType.TEST_DISCOVERY, 0.4),
        "pytest": (WorkflowType.TEST_DISCOVERY, 0.5),
        "architecture": (WorkflowType.ARCHITECTURE_MAP, 0.5),
        "structure": (WorkflowType.ARCHITECTURE_MAP, 0.3),
        "overview": (WorkflowType.ARCHITECTURE_MAP, 0.3),
        "organized": (WorkflowType.ARCHITECTURE_MAP, 0.3),
        "import": (WorkflowType.IMPORT_TRACING, 0.4),
        "depend": (WorkflowType.DEPENDENCY_GRAPH, 0.3),
        "call": (WorkflowType.CALL_GRAPH, 0.3),
        "rename": (WorkflowType.SAFE_REFACTORING, 0.5),
        "refactor": (WorkflowType.SAFE_REFACTORING, 0.5),
        "dead": (WorkflowType.DEAD_CODE, 0.5),
        "unused": (WorkflowType.DEAD_CODE, 0.5),
        "used": (WorkflowType.DEAD_CODE, 0.3),
        "compare": (WorkflowType.COMPARISON, 0.5),
        "differ": (WorkflowType.COMPARISON, 0.4),
        "search": (WorkflowType.TEXT_SEARCH, 0.3),
        "grep": (WorkflowType.TEXT_SEARCH, 0.5),
    }

    words = set(question.split())
    for word in words:
        for keyword, (wtype, weight) in keyword_map.items():
            if keyword in word:
                scores[wtype] = scores.get(wtype, 0.0) + weight

    if scores:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = min(scores[best] / 1.0, 0.7)  # cap at 0.7 for heuristic
        return ClassificationResult(
            workflow=best,
            confidence=confidence,
            method="keyword_heuristic",
        )

    # Ultimate fallback
    return ClassificationResult(
        workflow=WorkflowType.FEATURE_EXPLANATION,
        confidence=0.3,
        method="default",
    )
