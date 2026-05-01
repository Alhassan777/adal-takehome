"""Dependency ordering challenge: linear chains, diamonds, fan-out hubs.

Tests the agent's ability to determine correct dependency ordering between
files, detect diamond dependencies, identify high-impact hub modules, and
assess the blast radius of changes.
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

    # =========================================================
    # Pattern 1: Linear chain -- A -> B -> C -> D
    # =========================================================
    files["chain/__init__.py"] = ""
    chain_files = []
    chain_names = ["types", "validators", "services", "controllers"]
    for i, name in enumerate(chain_names):
        mod_file = f"chain/{name}.py"
        chain_files.append(mod_file)
        if i == 0:
            src = (
                f'"""Base types -- leaf dependency with no imports."""\n\n\n'
                f'class BaseType:\n'
                f'    """Foundational data type."""\n'
                f'    def __init__(self, value):\n'
                f'        self.value = value\n\n'
                f'    def serialize(self) -> str:\n'
                f'        return str(self.value)\n'
            )
        else:
            prev = chain_names[i - 1]
            src = (
                f'"""{name.title()} -- depends on {prev}."""\n\n'
                f'from .{prev} import *\n\n\n'
                f'def {name}_action(item):\n'
                f'    """Process an item at the {name} layer."""\n'
                f'    return {{"layer": "{name}", "item": str(item)}}\n'
            )
        src = _pad_with_helpers(src, target_lines, f"ch_{name[:3]}")
        files[mod_file] = src

    questions.append(GroundTruthQuestion(
        id="dep_q1",
        question="What is the correct dependency order for the chain/ package (leaf first)?",
        workflow_type="DEPENDENCY_GRAPH",
        expected={"ordered_files": chain_files},
        scoring=ScoringMethod.ORDERED_LIST_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # =========================================================
    # Pattern 2: Diamond -- A depends on B and C, both depend on D
    # =========================================================
    files["diamond/__init__.py"] = ""
    files["diamond/foundation.py"] = (
        '"""Foundation -- shared leaf dependency (bottom of diamond)."""\n\n\n'
        'class Foundation:\n'
        '    """Core class that both branches depend on."""\n'
        '    VERSION = "1.0"\n\n'
        '    @staticmethod\n'
        '    def create(name: str) -> dict:\n'
        '        return {"name": name, "version": Foundation.VERSION}\n'
    )
    files["diamond/branch_left.py"] = (
        '"""Left branch of the diamond -- depends on foundation."""\n\n'
        'from .foundation import Foundation\n\n\n'
        'class LeftProcessor:\n'
        '    def process(self, data):\n'
        '        base = Foundation.create("left")\n'
        '        base["data"] = data\n'
        '        return base\n'
    )
    files["diamond/branch_right.py"] = (
        '"""Right branch of the diamond -- depends on foundation."""\n\n'
        'from .foundation import Foundation\n\n\n'
        'class RightProcessor:\n'
        '    def process(self, data):\n'
        '        base = Foundation.create("right")\n'
        '        base["data"] = data\n'
        '        return base\n'
    )
    files["diamond/aggregator.py"] = (
        '"""Top of diamond -- depends on both branches."""\n\n'
        'from .branch_left import LeftProcessor\n'
        'from .branch_right import RightProcessor\n\n\n'
        'class Aggregator:\n'
        '    def __init__(self):\n'
        '        self.left = LeftProcessor()\n'
        '        self.right = RightProcessor()\n\n'
        '    def aggregate(self, data):\n'
        '        return {\n'
        '            "left": self.left.process(data),\n'
        '            "right": self.right.process(data),\n'
        '        }\n'
    )

    questions.append(GroundTruthQuestion(
        id="dep_q2",
        question="In the diamond/ package, what is the dependency structure? Which module is at the bottom?",
        workflow_type="DEPENDENCY_GRAPH",
        expected={
            "bottom": "diamond/foundation.py",
            "top": "diamond/aggregator.py",
            "pattern": "diamond",
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="dep_q3",
        question="If I change Foundation.create() in diamond/foundation.py, what files are affected?",
        workflow_type="IMPACT_ANALYSIS",
        expected={
            "affected_files": [
                "diamond/branch_left.py",
                "diamond/branch_right.py",
                "diamond/aggregator.py",
            ],
            "symbol": "create",
            "risk": "high",
        },
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # =========================================================
    # Pattern 3: Fan-out hub -- one core module imported by many
    # =========================================================
    fan_count = {SizeTier.XS: 3, SizeTier.S: 6, SizeTier.M: 12, SizeTier.L: 25, SizeTier.XL: 50}[size]

    files["hub/__init__.py"] = ""
    files["hub/core.py"] = (
        '"""Hub core -- the most-imported module in the project."""\n\n\n'
        'class CoreService:\n'
        '    """Central service used by all consumers."""\n\n'
        '    def execute(self, command: str) -> dict:\n'
        '        return {"command": command, "status": "ok"}\n\n\n'
        'def get_core_instance() -> CoreService:\n'
        '    """Factory function for CoreService."""\n'
        '    return CoreService()\n'
    )

    consumer_files = []
    for i in range(fan_count):
        consumer_file = f"hub/consumer_{i:03d}.py"
        consumer_files.append(consumer_file)
        src = (
            f'"""Consumer {i} -- depends on hub/core."""\n\n'
            f'from .core import CoreService, get_core_instance\n\n\n'
            f'def consumer_{i}_action():\n'
            f'    svc = get_core_instance()\n'
            f'    return svc.execute("action_{i}")\n'
        )
        src = _pad_with_helpers(src, target_lines, f"con{i}")
        files[consumer_file] = src

    questions.append(GroundTruthQuestion(
        id="dep_q4",
        question="Which module in hub/ is the most-imported? How many files depend on it?",
        workflow_type="REVERSE_IMPORT_TRACING",
        expected={
            "hub_file": "hub/core.py",
            "dependent_count": fan_count,
            "dependents": consumer_files,
        },
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="dep_q5",
        question="What is the impact of changing CoreService.execute() in hub/core.py?",
        workflow_type="IMPACT_ANALYSIS",
        expected={
            "symbol": "execute",
            "file": "hub/core.py",
            "affected_count": fan_count,
            "risk": "high",
        },
        scoring=ScoringMethod.RISK_LEVEL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="dep_q6",
        question="If I rename get_core_instance in hub/core.py, what would break?",
        workflow_type="BREAKING_CHANGE",
        expected={
            "symbol": "get_core_instance",
            "breaking_files": consumer_files,
            "risk": "high",
        },
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.HARD,
    ))

    return SyntheticRepo(
        repo_id=f"dependency_{size.value}",
        challenge="dependency",
        size_tier=size,
        files=files,
        questions=questions,
        description="Dependency patterns (linear chain, diamond, fan-out hub) for ordering and impact analysis",
    )
