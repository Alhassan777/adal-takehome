"""Dead code challenge: unused symbols, unreachable code.

Tests the agent's ability to detect functions and classes that are defined
but never called or imported from any reachable path, and to assess whether
symbols are safe to remove.
"""

from __future__ import annotations

from ..generator import (
    Difficulty,
    GroundTruthQuestion,
    ScoringMethod,
    SizeTier,
    SyntheticRepo,
    _pad_with_helpers,
)

_LINES = {SizeTier.XS: 18, SizeTier.S: 28, SizeTier.M: 45, SizeTier.L: 60, SizeTier.XL: 50}


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []
    target_lines = _LINES[size]

    # ===========================================================
    # Active code -- actually used from main.py
    # ===========================================================
    files["core/__init__.py"] = ""
    files["core/processor.py"] = (
        '"""Active processor -- imported and used."""\n\n\n'
        'class Processor:\n'
        '    """Main data processor."""\n\n'
        '    def run(self, data: list) -> list:\n'
        '        return [self._transform(item) for item in data]\n\n'
        '    def _transform(self, item):\n'
        '        return {"processed": item}\n'
    )
    files["core/config.py"] = (
        '"""Configuration -- imported and used."""\n\n\n'
        'DEFAULT_BATCH_SIZE = 100\n\n\n'
        'def get_config() -> dict:\n'
        '    return {"batch_size": DEFAULT_BATCH_SIZE, "debug": False}\n'
    )
    files["main.py"] = (
        '"""Entry point -- uses Processor and get_config."""\n\n'
        'from core.processor import Processor\n'
        'from core.config import get_config\n\n\n'
        'def main():\n'
        '    cfg = get_config()\n'
        '    proc = Processor()\n'
        '    data = list(range(cfg["batch_size"]))\n'
        '    return proc.run(data)\n\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    )

    # ===========================================================
    # Dead code -- defined but never imported or called
    # ===========================================================
    dead_symbols = []

    files["core/legacy_processor.py"] = (
        '"""Legacy processor -- COMPLETELY DEAD, never imported anywhere."""\n\n\n'
        'class LegacyProcessor:\n'
        '    """Old processor replaced by Processor. Not imported anywhere."""\n\n'
        '    def run(self, data: list) -> list:\n'
        '        return [{"legacy": item} for item in data]\n\n\n'
        'def legacy_init():\n'
        '    """Legacy initialization -- also dead."""\n'
        '    return LegacyProcessor()\n'
    )
    dead_symbols.extend([
        {"symbol": "LegacyProcessor", "file": "core/legacy_processor.py", "kind": "class"},
        {"symbol": "legacy_init", "file": "core/legacy_processor.py", "kind": "function"},
    ])

    files["core/experimental.py"] = (
        '"""Experimental features -- never imported."""\n\n\n'
        'def experimental_transform(data):\n'
        '    """WIP transform -- not used by anything."""\n'
        '    return [x ** 2 for x in data]\n\n\n'
        'class ExperimentalCache:\n'
        '    """Cache that was prototyped but never integrated."""\n\n'
        '    def __init__(self):\n'
        '        self._store = {}\n\n'
        '    def get(self, key):\n'
        '        return self._store.get(key)\n\n'
        '    def set(self, key, value):\n'
        '        self._store[key] = value\n'
    )
    dead_symbols.extend([
        {"symbol": "experimental_transform", "file": "core/experimental.py", "kind": "function"},
        {"symbol": "ExperimentalCache", "file": "core/experimental.py", "kind": "class"},
    ])

    # -- A function that IS imported but only by another dead module --
    files["core/orphan_utils.py"] = (
        '"""Utilities only used by dead code."""\n\n\n'
        'def format_legacy_output(data: dict) -> str:\n'
        '    """Only imported by legacy_processor -- transitively dead."""\n'
        '    return str(data)\n'
    )
    # Make legacy_processor import it
    files["core/legacy_processor.py"] = (
        '"""Legacy processor -- COMPLETELY DEAD, never imported anywhere."""\n\n'
        'from .orphan_utils import format_legacy_output\n\n\n'
        'class LegacyProcessor:\n'
        '    """Old processor replaced by Processor. Not imported anywhere."""\n\n'
        '    def run(self, data: list) -> list:\n'
        '        return [format_legacy_output({"legacy": item}) for item in data]\n\n\n'
        'def legacy_init():\n'
        '    """Legacy initialization -- also dead."""\n'
        '    return LegacyProcessor()\n'
    )
    dead_symbols.append(
        {"symbol": "format_legacy_output", "file": "core/orphan_utils.py", "kind": "function"},
    )

    # -- Internal helper used within its own file but file itself is dead --
    files["utils/deprecated.py"] = (
        '"""Deprecated utilities -- entire file is dead."""\n\n'
        'if False:  # pragma: no cover\n'
        '    # This import would create a dependency, but it is unreachable\n'
        '    from core.processor import Processor\n\n\n'
        'def old_slugify(text: str) -> str:\n'
        '    """Deprecated slugify -- replaced by a library."""\n'
        '    return text.lower().replace(" ", "_")\n\n\n'
        'def old_truncate(text: str, n: int = 50) -> str:\n'
        '    """Deprecated truncate."""\n'
        '    return text[:n]\n'
    )
    files["utils/__init__.py"] = ""
    dead_symbols.extend([
        {"symbol": "old_slugify", "file": "utils/deprecated.py", "kind": "function"},
        {"symbol": "old_truncate", "file": "utils/deprecated.py", "kind": "function"},
    ])

    # ===========================================================
    # Live symbols for contrast
    # ===========================================================
    live_symbols = [
        {"symbol": "Processor", "file": "core/processor.py", "kind": "class"},
        {"symbol": "get_config", "file": "core/config.py", "kind": "function"},
        {"symbol": "main", "file": "main.py", "kind": "function"},
    ]

    # ===========================================================
    # Questions
    # ===========================================================
    dead_symbol_names = [d["symbol"] for d in dead_symbols]
    dead_files = list({d["file"] for d in dead_symbols})

    questions.append(GroundTruthQuestion(
        id="dc_q1",
        question="Is the LegacyProcessor class still used anywhere in the codebase?",
        workflow_type="DEAD_CODE",
        expected={"symbol": "LegacyProcessor", "is_dead": True, "file": "core/legacy_processor.py"},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="dc_q2",
        question="Is it safe to delete core/experimental.py?",
        workflow_type="SAFE_REFACTORING",
        expected={"file": "core/experimental.py", "safe_to_delete": True, "references_elsewhere": False},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="dc_q3",
        question="format_legacy_output is imported by legacy_processor.py. But is legacy_processor.py itself used?",
        workflow_type="DEAD_CODE",
        expected={
            "symbol": "format_legacy_output",
            "is_dead": True,
            "reason": "only importer (legacy_processor.py) is itself dead",
        },
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="dc_q4",
        question="Which symbols in the codebase are never used (dead code)?",
        workflow_type="DEAD_CODE",
        expected={"dead_symbols": dead_symbol_names},
        scoring=ScoringMethod.SYMBOL_SET_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="dc_q5",
        question="Is the Processor class used? What references it?",
        workflow_type="DEAD_CODE",
        expected={"symbol": "Processor", "is_dead": False, "referenced_by": ["main.py"]},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- Scale up --
    _extra = {SizeTier.XS: 0, SizeTier.S: 3, SizeTier.M: 15, SizeTier.L: 50, SizeTier.XL: 140}
    for i in range(_extra[size]):
        mod = f"modules/mod_{i:03d}.py"
        if "modules/__init__.py" not in files:
            files["modules/__init__.py"] = ""
        is_dead = i % 3 == 0  # every 3rd filler module is dead
        if is_dead:
            src = (
                f'"""Module {i} -- dead filler."""\n\n\n'
                f'def dead_func_{i}():\n'
                f'    return {i}\n'
            )
        else:
            src = (
                f'"""Module {i} -- active filler."""\n\n'
                f'from core.config import get_config\n\n\n'
                f'def active_func_{i}():\n'
                f'    return get_config()\n'
            )
        src = _pad_with_helpers(src, target_lines, f"m{i}")
        files[mod] = src

    return SyntheticRepo(
        repo_id=f"dead_code_{size.value}",
        challenge="dead_code",
        size_tier=size,
        files=files,
        questions=questions,
        description="Mix of live and dead code to test unused symbol detection and safe-to-delete analysis",
    )
