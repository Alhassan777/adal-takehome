"""
LLM agent with ReAct-style tool-calling for Python codebase navigation.

The agent reasons over one or more tool calls before producing a final answer.
Tools are self-contained objects (Tool dataclass) that carry their own:
  - OpenAI function schema  (schema)
  - Python handler function (handler)
  - System-prompt blurb     (prompt_description)

TOOLS, HANDLERS, and the "Available tools" section of the system prompt are all
derived from REGISTRY — no duplication, one place to add or change a tool.
"""

import fnmatch
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openai import OpenAI

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────

_log = logging.getLogger(__name__)
_logging_configured = False


def _ensure_agent_logging() -> None:
    """Attach a default handler if the process has none (makes tool traces visible)."""
    global _logging_configured
    if _logging_configured:
        return
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
    _logging_configured = True


# ──────────────────────────────────────────────
# WORKSPACE ROOT (sandbox boundary)
# ──────────────────────────────────────────────

_WORKSPACE_ROOT = Path(__file__).resolve().parent


def _resolve_workspace_path(raw: str) -> Path:
    """Resolve a raw path string; raises ValueError if outside _WORKSPACE_ROOT."""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_WORKSPACE_ROOT / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(_WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"path must be under workspace {_WORKSPACE_ROOT}: {raw!r}"
        ) from exc
    return p


# ──────────────────────────────────────────────
# TOOL DATACLASS
# ──────────────────────────────────────────────

@dataclass
class Tool:
    """
    A self-contained tool definition.

    schema              — OpenAI function-calling schema dict (type + function keys).
    handler             — Python function (args: dict) -> str.
    prompt_description  — Short markdown block shown to the LLM in the system prompt.
    """
    schema: dict
    handler: Callable[[dict], str]
    prompt_description: str

    @property
    def name(self) -> str:
        return self.schema["function"]["name"]


# ──────────────────────────────────────────────
# TOOL IMPLEMENTATIONS
# ──────────────────────────────────────────────

def _tool_file_tree(args: dict) -> str:
    """Return an indented tree of files/dirs under a given path."""
    path_arg = args.get("path")
    if not path_arg or not isinstance(path_arg, str):
        return "Error: 'path' is required and must be a string."

    try:
        root = _resolve_workspace_path(path_arg)
    except ValueError as exc:
        return f"Error: {exc}"

    if not root.is_dir():
        return f"Error: not a directory or does not exist: {root}"

    glob_pattern = args.get("glob", "*")
    max_depth = args.get("max_depth", 3)
    if not isinstance(max_depth, int) or max_depth < 1:
        max_depth = 3

    lines: list[str] = [str(root)]

    def _walk(directory: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if entry.name.startswith("."):
                continue
            if entry.is_file() and not fnmatch.fnmatch(entry.name, glob_pattern):
                continue
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, depth + 1, prefix + extension)

    _walk(root, 1, "")
    return "\n".join(lines)


def _tool_read_file(args: dict) -> str:
    """Read a UTF-8 text file inside the workspace with an optional 1-based line range."""
    path_arg = args.get("path")
    if not path_arg or not isinstance(path_arg, str):
        return "Error: 'path' is required and must be a string."

    try:
        path = _resolve_workspace_path(path_arg)
    except ValueError as exc:
        return f"Error: {exc}"

    if not path.is_file():
        return f"Error: not a file or does not exist: {path}"

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error: could not read file: {exc}"

    start = args.get("start_line")
    end = args.get("end_line")

    if start is not None or end is not None:
        if start is not None and (not isinstance(start, int) or start < 1):
            return "Error: start_line must be a positive integer."
        if end is not None and (not isinstance(end, int) or end < 1):
            return "Error: end_line must be a positive integer."
        lines = text.splitlines(keepends=True)
        s = (start or 1) - 1
        e = end if end is not None else len(lines)
        if s >= len(lines):
            return f"(File has {len(lines)} lines; start_line {start} is past end.)"
        text = "".join(lines[s:e])
        return f"# {path} (lines {s + 1}-{min(e, len(lines))} of {len(lines)})\n{text}"

    return f"# {path}\n{text}"


def _tool_search_code(args: dict) -> str:
    """Search for a pattern in files under root_dir; returns file:line: content rows."""
    root_arg = args.get("root_dir")
    pattern_arg = args.get("pattern")

    if not root_arg or not isinstance(root_arg, str):
        return "Error: 'root_dir' is required and must be a string."
    if not pattern_arg or not isinstance(pattern_arg, str):
        return "Error: 'pattern' is required and must be a string."

    try:
        root = _resolve_workspace_path(root_arg)
    except ValueError as exc:
        return f"Error: {exc}"

    if not root.is_dir():
        return f"Error: not a directory or does not exist: {root}"

    glob_pattern = args.get("glob", "*.py")
    max_results = args.get("max_results", 50)
    if not isinstance(max_results, int) or max_results < 1:
        max_results = 50

    try:
        regex = re.compile(pattern_arg)
    except re.error as exc:
        return f"Error: invalid regex pattern: {exc}"

    matches: list[str] = []
    truncated = False

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        if not fnmatch.fnmatch(filepath.name, glob_pattern):
            continue
        try:
            for lineno, line in enumerate(
                filepath.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if regex.search(line):
                    matches.append(f"{filepath}:{lineno}: {line.rstrip()}")
                    if len(matches) >= max_results:
                        truncated = True
                        break
        except OSError:
            continue
        if truncated:
            break

    if not matches:
        return f"No matches for pattern {pattern_arg!r} under {root}."

    result = "\n".join(matches)
    if truncated:
        result += f"\n... (results capped at {max_results})"
    return result


# ──────────────────────────────────────────────
# TOOL REGISTRY  ← single source of truth
# ──────────────────────────────────────────────

REGISTRY: list[Tool] = [
    Tool(
        schema={
            "type": "function",
            "function": {
                "name": "file_tree",
                "description": (
                    "List files and directories under a given path as an indented tree. "
                    "Use this first to discover the codebase layout when you don't know "
                    "what files or directories exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Directory to list. Absolute or relative to workspace root "
                                "(e.g. /workspace/sample_project or sample_project)."
                            ),
                        },
                        "glob": {
                            "type": "string",
                            "description": "Filename filter applied to files only. Default: '*' (all files).",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "How many directory levels deep to traverse. Default: 3.",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        handler=_tool_file_tree,
        prompt_description=(
            "### file_tree\n"
            "List files and directories under a given path as an indented tree.\n"
            "Use this to discover the layout of the codebase before reading or searching.\n"
            "Required arg: path (directory; absolute or relative to workspace root)\n"
            "Optional arg: glob (filename filter, default \"*\")\n"
            "Optional arg: max_depth (how many levels deep, default 3)"
        ),
    ),
    Tool(
        schema={
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read the full contents of a file inside the workspace, "
                    "or a 1-based inclusive line range. "
                    "Use when you know the file path and want to inspect its source."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Absolute path under the workspace "
                                "(e.g. /workspace/sample_project/models.py) "
                                "or relative to the workspace root "
                                "(e.g. sample_project/models.py)."
                            ),
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "First line to return (1-based). Omit for full file.",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Last line to return (1-based, inclusive). Omit to read to end of file.",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        handler=_tool_read_file,
        prompt_description=(
            "### read_file\n"
            "Read the full text of a file inside the workspace, or a 1-based inclusive line range.\n"
            "Use this to inspect a file once you know its path.\n"
            "Required arg: path (absolute or relative to workspace root)\n"
            "Optional args: start_line (int), end_line (int)"
        ),
    ),
    Tool(
        schema={
            "type": "function",
            "function": {
                "name": "search_code",
                "description": (
                    "Search for a text pattern (substring or Python regex) across files "
                    "under a given directory. Returns matching lines with file path and "
                    "line number. Use when you don't know which file contains a symbol."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root_dir": {
                            "type": "string",
                            "description": (
                                "Directory to search under. Absolute or relative to workspace root "
                                "(e.g. /workspace/sample_project or sample_project)."
                            ),
                        },
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Substring or Python regex to match against each line. "
                                "Example: 'def truncate' or 'class \\w+'."
                            ),
                        },
                        "glob": {
                            "type": "string",
                            "description": "Filename glob filter. Default: '*.py'.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of matching lines to return. Default: 50.",
                        },
                    },
                    "required": ["root_dir", "pattern"],
                },
            },
        },
        handler=_tool_search_code,
        prompt_description=(
            "### search_code\n"
            "Search for a text pattern across files under a given directory.\n"
            "Use this when you need to locate a symbol without knowing which file it is in.\n"
            "Required arg: root_dir (absolute or relative workspace path to start the search)\n"
            "Required arg: pattern (substring or Python regex to match)\n"
            "Optional arg: glob (filename filter, default \"*.py\")\n"
            "Optional arg: max_results (cap on returned matches, default 50)"
        ),
    ),
]

# Derived views — used by the agent loop and OpenAI SDK; never edited manually.
TOOLS: list[dict] = [t.schema for t in REGISTRY]
HANDLERS: dict[str, Callable[[dict], str]] = {t.name: t.handler for t in REGISTRY}


# ──────────────────────────────────────────────
# SYSTEM PROMPT (assembled from REGISTRY)
# ──────────────────────────────────────────────

_TOOL_DOCS = "\n\n".join(t.prompt_description for t in REGISTRY)

AGENT_IDENTITY = f"""
You are a code navigation assistant for a Python codebase.

Your job: answer questions about symbol definitions, cross-file references, and code
structure by calling tools to read and search the source files.

## ReAct loop
1. THINK — briefly note what you know and what you still need.
2. ACT — call the most appropriate tool to get the missing information.
3. OBSERVE — read the tool result.
4. Repeat steps 1-3 until you have everything needed.
5. ANSWER — give a final answer that includes the requested code snippets and file names.

Never make up file contents. If a tool returns an error, try an alternative path or tool.
When you don't know what files or directories exist, call file_tree first to orient yourself.

## Available tools

{_TOOL_DOCS}
""".strip()

SYSTEM_PROMPT = AGENT_IDENTITY


# ──────────────────────────────────────────────
# AGENT LOOP
# ──────────────────────────────────────────────

MAX_TOOL_ROUNDS = 10


def run_agent(
    user_message: str,
    history: list[dict],
    model: str = "gpt-4o-mini",
) -> str:
    """
    ReAct agent loop: send message → handle tool calls → return final text response.
    Injects the system prompt on the first call (when history has no system message).
    Stops after MAX_TOOL_ROUNDS tool rounds regardless.
    """
    _ensure_agent_logging()
    client = OpenAI()

    if not any(m.get("role") == "system" for m in history):
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    history.append({"role": "user", "content": user_message})

    tool_rounds = 0

    while True:
        kwargs: dict = {"model": model, "messages": history}
        if TOOLS:
            kwargs["tools"] = TOOLS

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            final = choice.message.content or "(no response)"
            history.append({"role": "assistant", "content": final})
            return final

        if tool_rounds >= MAX_TOOL_ROUNDS:
            msg = f"(agent stopped after {MAX_TOOL_ROUNDS} tool rounds without a final answer)"
            _log.warning(msg)
            history.append({"role": "assistant", "content": msg})
            return msg

        history.append(choice.message)
        tool_rounds += 1

        for call in choice.message.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)

            _log.info("TOOL CALL  %s  args=%s", name, json.dumps(args))
            print(f"  [tool] {name}({json.dumps(args)})")

            handler = HANDLERS.get(name)
            if handler is None:
                result = f"Error: unknown tool '{name}'"
            else:
                try:
                    result = handler(args)
                except Exception as exc:
                    result = f"Error: {exc}"

            _log.info("TOOL RESULT %s => %s", name, result[:300])
            print(f"  [result] {result[:300]}{'...' if len(result) > 300 else ''}\n")

            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )


# ──────────────────────────────────────────────
# INTERACTIVE ENTRY POINT
# ──────────────────────────────────────────────

def main() -> None:
    _ensure_agent_logging()
    print("Code Navigation Agent  (type 'quit' to exit)")
    print("=" * 50)

    history: list[dict] = []

    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query or query.lower() in ("quit", "exit"):
            break

        print()
        try:
            answer = run_agent(query, history)
            print(f"\n{answer}")
        except Exception as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
