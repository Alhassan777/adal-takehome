"""Tests for the workflow engine: classifier, playbooks, fallbacks, and end-to-end."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.indexer import build_index
from codebase_agent.models import MentionedFile, ParsedQuery
from codebase_agent.workflows import create_engine
from codebase_agent.workflows.classifier import classify_question, ClassificationResult, extract_params
from codebase_agent.workflows.playbooks import PLAYBOOKS, get_playbook
from codebase_agent.workflows.types import TIER_MAP, WorkflowType
from codebase_agent.config import ExecutionMode

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


# ============================================================
# Classification Tests
# ============================================================


class TestClassifier:
    """Test the two-stage workflow classifier."""

    # --- Tier 1 ---

    def test_symbol_lookup_where_defined(self):
        r = classify_question("Where is User defined?")
        assert r.workflow == WorkflowType.SYMBOL_LOOKUP
        assert r.confidence >= 0.8
        assert r.extracted_params.get("target") == "user"

    def test_symbol_lookup_find(self):
        r = classify_question("find create_user")
        assert r.workflow == WorkflowType.SYMBOL_LOOKUP

    def test_file_listing(self):
        r = classify_question("What files are in the project?")
        assert r.workflow == WorkflowType.FILE_LISTING

    def test_file_reading(self):
        r = classify_question("Show me services.py")
        assert r.workflow == WorkflowType.FILE_READING
        assert "services.py" in r.extracted_params.get("target", "") or "services.py" in r.extracted_params.get("file", "")

    def test_text_search(self):
        r = classify_question("search for 'TODO' in the codebase")
        assert r.workflow == WorkflowType.TEXT_SEARCH

    # --- Tier 2 ---

    def test_goto_definition_with_hint(self):
        r = classify_question("What is `User` at line 2, character 21 in services.py?")
        assert r.workflow == WorkflowType.GOTO_DEFINITION_HINT
        assert r.extracted_params.get("line") == 2
        assert r.extracted_params.get("character") == 21

    def test_import_tracing(self):
        r = classify_question("What does services.py import?")
        assert r.workflow == WorkflowType.IMPORT_TRACING

    def test_reverse_import(self):
        r = classify_question("Who imports models.py?")
        assert r.workflow == WorkflowType.REVERSE_IMPORT_TRACING

    # --- Tier 3 ---

    def test_feature_explanation(self):
        r = classify_question("How does authentication work?")
        assert r.workflow == WorkflowType.FEATURE_EXPLANATION

    def test_feature_explain_variant(self):
        r = classify_question("Explain how the user creation flow works")
        assert r.workflow == WorkflowType.FEATURE_EXPLANATION

    def test_impact_analysis(self):
        r = classify_question("What breaks if I change create_user?")
        assert r.workflow == WorkflowType.IMPACT_ANALYSIS

    def test_impact_safe_to_change(self):
        r = classify_question("Is it safe to rename get_user?")
        assert r.workflow in (WorkflowType.IMPACT_ANALYSIS, WorkflowType.SAFE_REFACTORING)

    def test_test_discovery(self):
        r = classify_question("What tests cover services.py?")
        assert r.workflow == WorkflowType.TEST_DISCOVERY

    def test_call_graph(self):
        r = classify_question("What does summarize_project call?")
        assert r.workflow == WorkflowType.CALL_GRAPH

    def test_reverse_call_graph(self):
        r = classify_question("What calls format_date?")
        assert r.workflow == WorkflowType.REVERSE_CALL_GRAPH

    # --- Tier 4 ---

    def test_architecture_map(self):
        r = classify_question("What's the high-level architecture?")
        assert r.workflow == WorkflowType.ARCHITECTURE_MAP

    def test_module_overview(self):
        r = classify_question("Explain the services/ directory")
        assert r.workflow == WorkflowType.MODULE_OVERVIEW

    def test_api_surface(self):
        r = classify_question("What's the public API of models.py?")
        assert r.workflow == WorkflowType.API_SURFACE

    def test_dependency_graph(self):
        r = classify_question("Show me the dependency graph")
        assert r.workflow == WorkflowType.DEPENDENCY_GRAPH

    # --- Tier 5 ---

    def test_safe_refactoring(self):
        r = classify_question("Can I safely rename get_user to fetch_user?")
        assert r.workflow == WorkflowType.SAFE_REFACTORING

    def test_dead_code(self):
        r = classify_question("Is legacy_handler still used?")
        assert r.workflow == WorkflowType.DEAD_CODE

    def test_missing_tests(self):
        r = classify_question("What functions lack test coverage?")
        assert r.workflow == WorkflowType.MISSING_TESTS

    def test_breaking_change(self):
        r = classify_question("What happens if I remove the email field from User?")
        assert r.workflow == WorkflowType.BREAKING_CHANGE

    # --- Tier 6 ---

    def test_comparison(self):
        r = classify_question("How does create_user differ from create_admin?")
        assert r.workflow == WorkflowType.COMPARISON
        assert r.extracted_params.get("symbol_a") == "create_user"
        assert r.extracted_params.get("symbol_b") == "create_admin"

    def test_explicit_context(self):
        files = [MentionedFile(path="services.py", content_preview="", symbols=[])]
        r = classify_question("Explain @services.py", mentioned_files=files)
        assert r.workflow == WorkflowType.EXPLICIT_CONTEXT

    def test_follow_up(self):
        r = classify_question("Tell me more about that file", conversation_history=["prior context"])
        assert r.workflow == WorkflowType.FOLLOW_UP

    # --- Fallback ---

    def test_ambiguous_defaults_to_explanation(self):
        r = classify_question("something completely unrelated")
        assert r.workflow == WorkflowType.FEATURE_EXPLANATION
        assert r.method == "default"
        assert r.confidence < 0.5

    def test_keyword_heuristic(self):
        r = classify_question("any bugs in the authentication code?")
        # Should pick up "architecture" or fall back reasonably
        assert r.method in ("keyword_heuristic", "pattern", "default")


# ============================================================
# Playbook Tests
# ============================================================


class TestPlaybooks:
    """Test playbook registry and structure."""

    def test_all_workflow_types_have_playbooks(self):
        for wt in WorkflowType:
            assert wt in PLAYBOOKS, f"Missing playbook for {wt}"

    def test_playbook_has_required_fields(self):
        for wt, playbook in PLAYBOOKS.items():
            assert playbook.workflow_type == wt
            assert playbook.trigger_description
            assert playbook.required_tools
            assert playbook.strategy_steps
            assert playbook.output_format
            assert playbook.max_tool_rounds > 0

    def test_tier_budget_scaling(self):
        """Higher-tier workflows should generally have higher budgets."""
        tier1_budgets = [PLAYBOOKS[wt].max_tool_rounds for wt in WorkflowType if TIER_MAP.get(wt) == 1]
        tier3_budgets = [PLAYBOOKS[wt].max_tool_rounds for wt in WorkflowType if TIER_MAP.get(wt) == 3]
        assert max(tier1_budgets) <= max(tier3_budgets)

    def test_get_playbook(self):
        pb = get_playbook(WorkflowType.IMPACT_ANALYSIS)
        assert pb.workflow_type == WorkflowType.IMPACT_ANALYSIS
        assert "find_references" in pb.required_tools


# ============================================================
# Engine End-to-End Tests
# ============================================================


@pytest.mark.skip(reason="Legacy playbook engine removed; see test_engine_modes.py for new engine tests")
class TestAgentLoopEngine:
    """End-to-end tests for the removed playbook engine (kept as reference)."""

    @classmethod
    def setup_class(cls):
        cls.index = build_index(SAMPLE_REPO)
        cls.engine = None

    def _query(self, question: str, mentioned_files=None) -> dict:
        parsed = ParsedQuery(
            raw_query=question,
            clean_query=question,
            mentioned_files=mentioned_files or [],
        )
        return self.engine.answer(parsed)

    # --- Tier 1 ---

    def test_symbol_lookup_user(self):
        result = self._query("Where is User defined?")
        assert result["workflow_type"] == "symbol_lookup"
        assert any("models" in f for f in result["relevant_files"])

    def test_file_listing(self):
        result = self._query("What files are in the project?")
        assert result["workflow_type"] == "file_listing"
        assert result["tool_calls_made"] >= 1

    def test_text_search(self):
        result = self._query("search for 'format_date' in the codebase")
        assert result["workflow_type"] == "text_search"

    # --- Tier 2 ---

    def test_goto_definition_no_file(self):
        result = self._query("Find where truncate is defined")
        assert any("utils" in f for f in result["relevant_files"])

    def test_import_tracing(self):
        result = self._query("What does services.py import?")
        assert result["workflow_type"] == "import_tracing"

    # --- Tier 3 ---

    def test_feature_explanation(self):
        result = self._query("How does the project summarization work?")
        assert result["workflow_type"] == "feature_explanation"
        assert result["tool_calls_made"] >= 2

    def test_impact_analysis(self):
        result = self._query("What breaks if I change create_user?")
        assert result["workflow_type"] == "impact_analysis"
        assert "findings" in result

    def test_test_discovery(self):
        result = self._query("What tests cover models.py?")
        assert result["workflow_type"] == "test_discovery"

    def test_call_graph(self):
        result = self._query("What does summarize_project call?")
        assert result["workflow_type"] == "call_graph"
        assert "findings" in result

    # --- Tier 4 ---

    def test_architecture_map(self):
        result = self._query("What's the high-level architecture?")
        assert result["workflow_type"] == "architecture_map"
        assert result["tool_calls_made"] >= 1

    # --- Tier 5 ---

    def test_dead_code_used_symbol(self):
        result = self._query("Is format_date still used?")
        assert result["workflow_type"] == "dead_code"
        findings = result["findings"]
        assert any(f.get("verdict") == "used" for f in findings if isinstance(f, dict))

    def test_safe_refactoring(self):
        result = self._query("Can I safely rename load_config?")
        assert result["workflow_type"] == "safe_refactoring"
        assert "findings" in result

    # --- Tier 6 ---

    def test_comparison(self):
        result = self._query("How does create_user differ from create_project?")
        assert result["workflow_type"] == "comparison"
        assert "findings" in result

    def test_explicit_context(self):
        mentioned = [MentionedFile(path="services.py", content_preview="", symbols=[])]
        result = self._query("Explain @services.py", mentioned_files=mentioned)
        assert result["workflow_type"] == "explicit_context"

    # --- Fallback behavior ---

    def test_fallback_on_missing_symbol(self):
        result = self._query("Where is nonexistent_xyz_123 defined?")
        assert result["workflow_type"] == "symbol_lookup"
        assert result["fallback_triggered"] is True

    def test_budget_enforcement(self):
        result = self._query("What functions lack test coverage?")
        playbook = get_playbook(WorkflowType.MISSING_TESTS)
        assert result["tool_calls_made"] <= playbook.max_tool_rounds

    # --- Answer structure ---

    def test_answer_has_required_fields(self):
        result = self._query("Where is User defined?")
        required_keys = [
            "question", "workflow_type", "tier", "classification_confidence",
            "classification_method", "relevant_files", "relevant_symbols",
            "findings", "tool_calls_made", "early_terminated",
            "fallback_triggered", "summary",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_summary_structure(self):
        result = self._query("Where is User defined?")
        summary = result["summary"]
        assert "question_type" in summary
        assert "files_analyzed" in summary
        assert "symbols_found" in summary
        assert "tools_called" in summary
        assert "confidence" in summary


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
