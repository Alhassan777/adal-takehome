"""
End-to-end test for the agent's code navigation capability.
Sends natural language queries through the full agent loop and verifies
the LLM correctly resolves symbol definitions.

Run inside Docker:
    docker compose run --rm interview-lsp python test.py
"""

import sys
from agent import run_agent


def test(name, query, expected_strings):
    """Run a query through the agent and check the response contains expected info."""
    print(f"\n{'=' * 60}")
    print(f"🧪 {name}")
    print(f"   📝 Query: {query}")

    history = []
    answer = run_agent(query, history)

    print(f"   💬 Answer: {answer[:500]}{'...' if len(answer) > 500 else ''}")

    ok = True
    for expected in expected_strings:
        if expected.lower() in answer.lower():
            print(f"   ✅ Found: '{expected}'")
        else:
            print(f"   ❌ Missing: '{expected}'")
            ok = False

    return ok


def main():
    passed = 0
    failed = 0
    tests = [
        (
            "Find definition of User",
            "Use your tools to find where `User` is defined. "
            "It's used at line 2, character 21 in /workspace/sample_project/services.py. "
            "Show the complete definition including all fields and methods.",
            ["class User", "models.py", "display_name"],
        ),
        (
            "Find definition of Task",
            "Use your tools to find the definition of `Task` at line 2, "
            "character 28 in /workspace/sample_project/services.py. "
            "Show the complete definition including all fields and methods.",
            ["class Task", "models.py", "completed"],
        ),
        (
            "Find definition of format_date",
            "Find where `format_date` is defined in /workspace/sample_project/services.py. "
            "Use your tools to read the file, locate the symbol, and jump to its definition. "
            "Show the complete function implementation.",
            ["def format_date", "utils.py", "strftime"],
        ),
        (
            "Read and navigate - find Project",
            "Find where `Project` is defined in /workspace/sample_project/services.py. "
            "Use your tools to read the file, locate the symbol, and jump to its definition. "
            "Show the full class definition.",
            ["project", "models.py", "pending_tasks"],
        ),
        (
            "Find truncate without knowing the file",
            "Find the definition of the `truncate` function in the project at /workspace/sample_project. "
            "Use your tools to search for it, then jump to its definition. "
            "Show the complete function implementation and mention which file it's in.",
            ["def truncate", "utils.py", "length"],
        ),
        (
            "Find pending_tasks without knowing the file",
            "Find the definition of the `pending_tasks` method in the project at /workspace/sample_project. "
            "Use your tools to search for it, then jump to its definition. "
            "Show the complete method implementation and mention which file it's in.",
            ["pending_tasks", "models.py", "completed"],
        ),
    ]

    for name, query, expected in tests:
        try:
            if test(name, query, expected):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
