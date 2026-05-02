"""Tests for tool_reflector.py -- post-answer tool suggestion with user approval."""

import json
from unittest.mock import MagicMock, patch

import pytest

from codebase_agent.workflows.tool_reflector import ToolProposal, ToolReflector


@pytest.fixture
def mock_client():
    """Mock OpenAI client."""
    return MagicMock()


@pytest.fixture
def reflector(mock_client):
    return ToolReflector(client=mock_client)


SAMPLE_MESSAGES = [
    {"role": "system", "content": "You are a codebase navigation agent..."},
    {"role": "user", "content": "How does authentication work?"},
    {"role": "assistant", "content": "auth_symbols = [s for s in index.symbols if 'auth' in s.name.lower()]"},
    {"role": "user", "content": "REPL output:\n[SymbolRecord(name='authenticate', ...)]"},
    {"role": "assistant", "content": "answer['content'] = 'Auth uses JWT tokens'\nanswer['ready'] = True"},
]


def _make_response(proposals: list[dict]) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps({"proposals": proposals})
    return response


VALID_PROPOSAL = {
    "name": "find_auth_symbols",
    "description": "Find all authentication-related symbols in the codebase.",
    "code": "def find_auth_symbols(index):\n    return [s for s in index.symbols if 'auth' in s.name.lower()]",
    "test_cases": [{"input": {}, "expected_contains": "auth"}],
    "rationale": "Reusable pattern for finding auth-related code across codebases.",
}


class TestToolProposal:
    def test_to_dict_roundtrip(self):
        proposal = ToolProposal(
            name="my_tool",
            description="Does something",
            code="def my_tool(): pass",
            test_cases=[{"input": {}, "expected_contains": ""}],
            rationale="Useful",
        )
        d = proposal.to_dict()
        assert d["name"] == "my_tool"
        assert d["description"] == "Does something"
        assert d["code"] == "def my_tool(): pass"
        assert len(d["test_cases"]) == 1
        assert d["rationale"] == "Useful"


class TestReflect:
    def test_returns_proposals_on_valid_response(self, reflector, mock_client):
        mock_client.chat.completions.create.return_value = _make_response([VALID_PROPOSAL])

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert len(proposals) == 1
        assert proposals[0].name == "find_auth_symbols"
        assert proposals[0].description == "Find all authentication-related symbols in the codebase."
        assert "def find_auth_symbols" in proposals[0].code

    def test_returns_empty_on_no_proposals(self, reflector, mock_client):
        mock_client.chat.completions.create.return_value = _make_response([])

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert proposals == []

    def test_returns_empty_on_api_failure(self, reflector, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("API error")

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert proposals == []

    def test_caps_at_three_proposals(self, reflector, mock_client):
        proposals_raw = [
            {**VALID_PROPOSAL, "name": f"tool_{i}"}
            for i in range(5)
        ]
        mock_client.chat.completions.create.return_value = _make_response(proposals_raw)

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert len(proposals) == 3

    def test_skips_incomplete_proposals(self, reflector, mock_client):
        incomplete = [
            VALID_PROPOSAL,
            {"name": "no_code", "description": "Missing code", "test_cases": [{"input": {}}], "rationale": "x"},
            {"name": "", "code": "def x(): pass", "description": "No name", "test_cases": [{"input": {}}], "rationale": "x"},
        ]
        mock_client.chat.completions.create.return_value = _make_response(incomplete)

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert len(proposals) == 1
        assert proposals[0].name == "find_auth_symbols"

    def test_uses_sub_model(self, reflector, mock_client):
        mock_client.chat.completions.create.return_value = _make_response([])

        reflector.reflect(SAMPLE_MESSAGES)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_skips_system_messages_in_conversation(self, reflector, mock_client):
        mock_client.chat.completions.create.return_value = _make_response([])

        reflector.reflect(SAMPLE_MESSAGES)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_content = call_kwargs["messages"][1]["content"]
        assert "You are a codebase navigation agent" not in user_content
        assert "How does authentication work?" in user_content

    def test_handles_malformed_json(self, reflector, mock_client):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = '{"proposals": "not a list"}'
        mock_client.chat.completions.create.return_value = response

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert proposals == []

    def test_handles_non_dict_items(self, reflector, mock_client):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = json.dumps({"proposals": ["string_item", 42, None]})
        mock_client.chat.completions.create.return_value = response

        proposals = reflector.reflect(SAMPLE_MESSAGES)

        assert proposals == []


class TestSummarizeConversation:
    def test_formats_messages_correctly(self, reflector):
        summary = reflector._summarize_conversation(SAMPLE_MESSAGES)

        assert "[USER]" in summary
        assert "[AGENT CODE]" in summary
        assert "How does authentication work?" in summary
        assert "auth_symbols" in summary
        assert "REPL output:" in summary

    def test_excludes_system_messages(self, reflector):
        summary = reflector._summarize_conversation(SAMPLE_MESSAGES)

        assert "You are a codebase navigation agent" not in summary

    def test_truncates_long_messages(self, reflector):
        long_messages = [
            {"role": "user", "content": "x" * 5000},
        ]
        summary = reflector._summarize_conversation(long_messages)

        assert len(summary) <= 2100


class TestParseProposals:
    def test_parses_valid_proposals(self, reflector):
        raw = {"proposals": [VALID_PROPOSAL]}
        proposals = reflector._parse_proposals(raw)
        assert len(proposals) == 1
        assert isinstance(proposals[0], ToolProposal)

    def test_returns_empty_on_missing_key(self, reflector):
        assert reflector._parse_proposals({}) == []
        assert reflector._parse_proposals({"other": []}) == []

    def test_returns_empty_on_non_list(self, reflector):
        assert reflector._parse_proposals({"proposals": "not a list"}) == []

    def test_rejects_proposal_without_name(self, reflector):
        raw = {"proposals": [{
            "code": "def x(): pass",
            "description": "y",
            "test_cases": [{"input": {}}],
            "rationale": "z",
        }]}
        assert reflector._parse_proposals(raw) == []

    def test_rejects_proposal_without_test_cases(self, reflector):
        raw = {"proposals": [{
            "name": "x",
            "code": "def x(): pass",
            "description": "y",
            "test_cases": [],
            "rationale": "z",
        }]}
        assert reflector._parse_proposals(raw) == []
