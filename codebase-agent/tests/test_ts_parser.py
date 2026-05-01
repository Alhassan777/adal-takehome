"""Tests for ts_parser.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core.ts_parser import parse_file

SAMPLE_REPO = Path(__file__).parent.parent / "examples" / "sample_repo"


def test_parse_models_extracts_classes():
    result = parse_file(str(SAMPLE_REPO / "models.py"))
    names = [s.name for s in result.symbols]
    assert "User" in names
    assert "Task" in names
    assert "Project" in names


def test_parse_models_extracts_methods():
    result = parse_file(str(SAMPLE_REPO / "models.py"))
    names = [s.name for s in result.symbols]
    assert "display_name" in names
    assert "assign_to" in names
    assert "mark_done" in names
    assert "pending_tasks" in names


def test_parse_services_extracts_functions():
    result = parse_file(str(SAMPLE_REPO / "services.py"))
    names = [s.name for s in result.symbols]
    assert "create_user" in names
    assert "create_project" in names
    assert "summarize_project" in names


def test_parse_services_extracts_imports():
    result = parse_file(str(SAMPLE_REPO / "services.py"))
    modules = [i.module for i in result.imports if i.module]
    assert "datetime" in modules


def test_parse_extracts_identifier_refs():
    result = parse_file(str(SAMPLE_REPO / "services.py"))
    assert len(result.identifier_refs) > 0
    assert "Project" in result.identifier_refs or "User" in result.identifier_refs


def test_parse_extracts_signatures():
    result = parse_file(str(SAMPLE_REPO / "services.py"))
    create_user = next(s for s in result.symbols if s.name == "create_user")
    assert create_user.signature is not None
    assert "create_user" in create_user.signature


def test_parse_nonexistent_file():
    result = parse_file("/nonexistent/path.py")
    assert result.symbols == []


def test_parse_extracts_decorators(tmp_path):
    source = (
        'from fastapi import FastAPI\n\n'
        'app = FastAPI()\n\n\n'
        '@app.get("/users")\n'
        'def list_users():\n'
        '    return []\n\n\n'
        '@app.post("/users")\n'
        'def create_user(data: dict):\n'
        '    return data\n\n\n'
        '@app.delete("/users/{user_id}")\n'
        'async def delete_user(user_id: int):\n'
        '    pass\n\n\n'
        'def plain_helper():\n'
        '    return 42\n'
    )
    p = tmp_path / "routes.py"
    p.write_text(source)
    result = parse_file(str(p))

    by_name = {s.name: s for s in result.symbols}
    assert by_name["list_users"].decorators == ['@app.get("/users")']
    assert by_name["create_user"].decorators == ['@app.post("/users")']
    assert by_name["delete_user"].decorators == ['@app.delete("/users/{user_id}")']
    assert by_name["plain_helper"].decorators == []
