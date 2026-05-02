"""Learned Tool Registry -- agent-synthesized tools with Observer-pattern critic validation.

Inspired by:
- Voyager: skill library as executable code, compositionality, self-verification
- AutoAgents: Observer pattern for independent LLM evaluation of generated artifacts

Lifecycle:
1. Agent notices a reusable pattern while answering a question
2. Agent calls register_tool(name, code, description, test_cases) in the REPL
3. Stage 1: Deterministic validation -- compile code, run test cases
4. Stage 2: Observer critic -- gpt-4o-mini independently evaluates quality
5. If both pass: tool promoted to persistent library
6. On next session: learned tools appear as learned_* in the namespace
7. Learned tools can call other learned tools (compositionality)
8. Usage telemetry informs LRU eviction when cap (20) exceeded
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config import MAX_LEARNED_TOOLS, OPENAI_SUB_MODEL

_VALID_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


CRITIC_SYSTEM_PROMPT = """You are a code quality critic. Evaluate a proposed reusable tool function on these criteria:

1. **Correctness** (1-5): Does the code do what the description claims? Are edge cases handled?
2. **Generalizability** (1-5): Will this tool be useful across different codebases, or is it too specific?
3. **Non-redundancy** (1-5): Does it provide value beyond the existing built-in tools?
4. **Safety** (1-5): Could this code cause harm (file deletion, network calls, infinite loops)?

Respond in JSON:
{
    "correctness": <int 1-5>,
    "generalizability": <int 1-5>,
    "non_redundancy": <int 1-5>,
    "safety": <int 1-5>,
    "overall_score": <float, average of above>,
    "approved": <bool, true if overall_score >= 3.5>,
    "feedback": "<string, 1-2 sentence explanation>"
}"""


class LearnedToolRegistry:
    """Per-codebase registry of agent-synthesized tools."""

    def __init__(self, cache_dir: Path, openai_client):
        self.tools_dir = cache_dir / "learned_tools"
        self.manifest_path = self.tools_dir / "manifest.json"
        self._client = openai_client
        self._manifest: list[dict] = []
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load the manifest of known tools from disk."""
        if self.manifest_path.exists():
            try:
                self._manifest = json.loads(self.manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._manifest = []
        else:
            self._manifest = []

    def _save_manifest(self) -> None:
        """Persist manifest to disk atomically (write + rename)."""
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.tools_dir), suffix=".tmp")
        try:
            with open(fd, "w") as f:
                json.dump(self._manifest, f, indent=2)
            Path(tmp).replace(self.manifest_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def propose_tool(
        self,
        name: str,
        code: str,
        description: str,
        test_cases: list[dict],
    ) -> dict:
        """Agent proposes a new tool. Two-stage validation before promotion.

        Args:
            name: Snake_case tool name (e.g., 'find_django_views')
            code: Python function source code (must define a function named `name`)
            description: What the tool does
            test_cases: List of {"input": {...}, "expected_contains": str} dicts

        Returns:
            {"approved": bool, "feedback": str}
        """
        if not _VALID_TOOL_NAME_RE.match(name):
            return {
                "approved": False,
                "feedback": f"Invalid tool name '{name}'. Must be lowercase snake_case (a-z, 0-9, _), 1-64 chars, starting with a letter.",
            }

        existing_names = {t["name"] for t in self._manifest}
        if name in existing_names:
            return {"approved": False, "feedback": f"Tool '{name}' already exists. Use a different name."}

        stage1 = self._validate_deterministic(name, code, test_cases)
        if not stage1["passed"]:
            return {"approved": False, "feedback": f"Stage 1 failed: {stage1['error']}"}

        stage2 = self._observer_critic(name, code, description, stage1["test_results"])
        if not stage2["approved"]:
            return {"approved": False, "feedback": f"Critic rejected: {stage2['feedback']}"}

        self._promote_tool(name, code, description, stage2)
        return {"approved": True, "feedback": f"Tool '{name}' approved and saved. Score: {stage2['overall_score']:.1f}/5.0"}

    def _validate_deterministic(self, name: str, code: str, test_cases: list[dict]) -> dict:
        """Stage 1: Compile and run test cases."""
        try:
            compiled = compile(code, f"<learned_{name}>", "exec")
        except SyntaxError as e:
            return {"passed": False, "error": f"Syntax error: {e}"}

        namespace: dict[str, Any] = {}
        try:
            exec(compiled, namespace)
        except Exception as e:
            return {"passed": False, "error": f"Execution error during definition: {e}"}

        if name not in namespace:
            return {"passed": False, "error": f"Code must define a function named '{name}'"}

        fn = namespace[name]
        if not callable(fn):
            return {"passed": False, "error": f"'{name}' is not callable"}

        test_results = []
        for i, tc in enumerate(test_cases):
            try:
                result = fn(**tc.get("input", {}))
                result_str = str(result)
                expected = tc.get("expected_contains", "")
                passed = expected in result_str if expected else True
                test_results.append({"index": i, "passed": passed, "result": result_str[:500]})
            except Exception as e:
                test_results.append({"index": i, "passed": False, "result": f"Error: {e}"})

        all_passed = all(t["passed"] for t in test_results)
        if not all_passed:
            failures = [t for t in test_results if not t["passed"]]
            return {"passed": False, "error": f"{len(failures)} test(s) failed: {failures[0]['result']}", "test_results": test_results}

        return {"passed": True, "test_results": test_results}

    def _observer_critic(self, name: str, code: str, description: str, test_results: list[dict]) -> dict:
        """Stage 2: Independent LLM critic evaluates the tool.

        Uses gpt-4o-mini as an independent observer (AutoAgents pattern).
        """
        user_prompt = f"""Evaluate this proposed reusable tool:

**Name**: {name}
**Description**: {description}

**Code**:
```python
{code}
```

**Test Results**:
{json.dumps(test_results, indent=2)}

Evaluate on correctness, generalizability, non-redundancy, and safety."""

        try:
            response = self._client.chat.completions.create(
                model=OPENAI_SUB_MODEL,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            if "approved" not in result:
                score = result.get("overall_score", 0)
                result["approved"] = score >= 3.5
            return result
        except Exception as e:
            return {"approved": False, "feedback": f"Critic call failed: {e}", "overall_score": 0}

    def _promote_tool(self, name: str, code: str, description: str, critic_result: dict) -> None:
        """Save approved tool to disk and update manifest."""
        self.tools_dir.mkdir(parents=True, exist_ok=True)

        tool_file = (self.tools_dir / f"{name}.py").resolve()
        if not str(tool_file).startswith(str(self.tools_dir.resolve())):
            raise ValueError(f"Tool file path escapes tools_dir: {tool_file}")
        tool_file.write_text(code)

        entry = {
            "name": name,
            "description": description,
            "file": f"{name}.py",
            "created_at": time.time(),
            "last_used": time.time(),
            "use_count": 0,
            "critic_score": critic_result.get("overall_score", 0),
            "approved_by_critic": True,
        }
        self._manifest.append(entry)

        self._enforce_cap()
        self._save_manifest()

    def _enforce_cap(self) -> None:
        """Evict LRU tools when cap is exceeded."""
        if len(self._manifest) <= MAX_LEARNED_TOOLS:
            return

        sorted_tools = sorted(self._manifest, key=lambda t: t.get("last_used", 0))
        to_evict = sorted_tools[: len(self._manifest) - MAX_LEARNED_TOOLS]

        for entry in to_evict:
            tool_file = self._safe_tool_path(entry["file"])
            if tool_file is not None and tool_file.exists():
                tool_file.unlink()
            self._manifest.remove(entry)

    def _safe_tool_path(self, filename: str) -> Path | None:
        """Resolve a tool filename and verify it stays inside tools_dir."""
        tool_file = (self.tools_dir / filename).resolve()
        if not str(tool_file).startswith(str(self.tools_dir.resolve())):
            return None
        return tool_file

    def get_active_tools(self, index_hash: str) -> dict[str, Any]:
        """Return validated tools as callables. Supports compositionality."""
        active: dict[str, Any] = {}

        for entry in self._manifest:
            tool_file = self._safe_tool_path(entry["file"])
            if tool_file is None or not tool_file.exists():
                continue

            code = tool_file.read_text()
            namespace: dict[str, Any] = {}
            try:
                exec(compile(code, str(tool_file), "exec"), namespace)
                fn = namespace.get(entry["name"])
                if callable(fn):
                    active[entry["name"]] = fn
            except Exception:
                continue

        for name, fn in list(active.items()):
            fn.__globals__.update({f"learned_{n}": f for n, f in active.items()})

        return active

    def inject_into_namespace(self, namespace: dict, index_hash: str) -> None:
        """Add learned tools to the REPL namespace with the learned_ prefix."""
        active = self.get_active_tools(index_hash)
        for name, fn in active.items():
            namespace[f"learned_{name}"] = fn
        namespace["register_tool"] = self.propose_tool

    def record_usage(self, tool_name: str) -> None:
        """Track usage for telemetry and LRU eviction."""
        for entry in self._manifest:
            if entry["name"] == tool_name:
                entry["use_count"] = entry.get("use_count", 0) + 1
                entry["last_used"] = time.time()
                self._save_manifest()
                break

    def list_tools(self) -> list[dict]:
        """Return metadata for all learned tools."""
        return [
            {
                "name": e["name"],
                "description": e["description"],
                "use_count": e.get("use_count", 0),
                "critic_score": e.get("critic_score", 0),
            }
            for e in self._manifest
        ]
