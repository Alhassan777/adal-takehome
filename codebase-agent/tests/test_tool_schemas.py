"""Tests for tool_schemas.py -- OpenAI function-calling schema generation."""

import pytest

from codebase_agent.workflows.tool_schemas import (
    TOOL_DESCRIPTIONS,
    TOOL_PARAMETERS,
    build_openai_tool_schemas,
    build_tool_signatures_text,
)


class TestBuildOpenAIToolSchemas:
    def test_returns_list(self):
        schemas = build_openai_tool_schemas()
        assert isinstance(schemas, list)

    def test_schema_count_matches_descriptions(self):
        schemas = build_openai_tool_schemas()
        assert len(schemas) == len(TOOL_DESCRIPTIONS)

    def test_each_schema_has_required_structure(self):
        schemas = build_openai_tool_schemas()
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            fn = schema["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"

    def test_all_tool_names_present(self):
        schemas = build_openai_tool_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert names == set(TOOL_DESCRIPTIONS.keys())

    def test_required_params_are_lists(self):
        schemas = build_openai_tool_schemas()
        for schema in schemas:
            params = schema["function"]["parameters"]
            assert isinstance(params.get("required", []), list)

    def test_search_symbols_has_query_required(self):
        schemas = build_openai_tool_schemas()
        sym_schema = next(s for s in schemas if s["function"]["name"] == "search_symbols_tool")
        assert "query" in sym_schema["function"]["parameters"]["required"]

    def test_list_tree_has_no_required_params(self):
        schemas = build_openai_tool_schemas()
        tree_schema = next(s for s in schemas if s["function"]["name"] == "list_tree")
        assert tree_schema["function"]["parameters"]["required"] == []


class TestBuildToolSignaturesText:
    def test_returns_string(self):
        text = build_tool_signatures_text()
        assert isinstance(text, str)

    def test_contains_all_tool_names(self):
        text = build_tool_signatures_text()
        for name in TOOL_DESCRIPTIONS:
            assert f"tools.{name}" in text

    def test_contains_descriptions(self):
        text = build_tool_signatures_text()
        for desc in TOOL_DESCRIPTIONS.values():
            assert desc in text

    def test_contains_parameter_names(self):
        text = build_tool_signatures_text()
        assert "query: string" in text
        assert "file_path: string" in text
        assert "symbol_name: string" in text


class TestToolDescriptionsCompleteness:
    def test_all_tools_have_parameters(self):
        for name in TOOL_DESCRIPTIONS:
            assert name in TOOL_PARAMETERS, f"{name} missing from TOOL_PARAMETERS"

    def test_parameters_have_valid_types(self):
        valid_types = {"string", "integer", "boolean", "number", "array", "object"}
        for name, params in TOOL_PARAMETERS.items():
            for prop_name, prop in params.get("properties", {}).items():
                assert prop.get("type") in valid_types, f"{name}.{prop_name} has invalid type"
