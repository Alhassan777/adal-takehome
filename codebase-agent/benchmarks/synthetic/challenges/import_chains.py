"""Import chain challenge: re-exports, aliases, relative imports, circular imports.

Tests the agent's ability to trace imports through layers of indirection --
__init__.py re-exports, aliased imports, relative imports, and circular
dependency patterns that are resolved at function level.
"""

from __future__ import annotations

from ..generator import (
    Difficulty,
    GroundTruthQuestion,
    ScoringMethod,
    SizeTier,
    SyntheticRepo,
    _make_function,
    _pad_with_helpers,
)


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []

    # -- Core package with re-exports --
    files["core/__init__.py"] = (
        '"""Core package -- re-exports key symbols for convenience."""\n\n'
        'from .engine import Engine\n'
        'from .config import Config\n'
        'from .registry import Registry\n'
    )
    files["core/engine.py"] = (
        '"""Core execution engine."""\n\n'
        'from .config import Config\n\n\n'
        'class Engine:\n'
        '    """Main engine that orchestrates processing."""\n\n'
        '    def __init__(self, config: Config):\n'
        '        self.config = config\n'
        '        self._running = False\n\n'
        '    def start(self):\n'
        '        self._running = True\n'
        '        return self\n\n'
        '    def stop(self):\n'
        '        self._running = False\n'
    )
    files["core/config.py"] = (
        '"""Configuration management."""\n\n\n'
        'class Config:\n'
        '    """Application configuration holder."""\n\n'
        '    def __init__(self, debug: bool = False, port: int = 8080):\n'
        '        self.debug = debug\n'
        '        self.port = port\n\n'
        '    def as_dict(self) -> dict:\n'
        '        return {"debug": self.debug, "port": self.port}\n'
    )
    files["core/registry.py"] = (
        '"""Plugin registry for dynamically loaded components."""\n\n\n'
        'class Registry:\n'
        '    """Holds registered plugins by name."""\n\n'
        '    def __init__(self):\n'
        '        self._plugins: dict[str, object] = {}\n\n'
        '    def register(self, name: str, plugin: object):\n'
        '        self._plugins[name] = plugin\n\n'
        '    def get(self, name: str) -> object:\n'
        '        return self._plugins[name]\n\n'
        '    def list_plugins(self) -> list[str]:\n'
        '        return list(self._plugins.keys())\n'
    )

    # -- Consumer that imports via the __init__ re-export --
    files["app.py"] = (
        '"""Application layer that uses core package re-exports."""\n\n'
        'from core import Engine, Config\n\n\n'
        'def create_app():\n'
        '    """Bootstrap the application."""\n'
        '    config = Config(debug=True)\n'
        '    engine = Engine(config)\n'
        '    return engine.start()\n'
    )

    questions.append(GroundTruthQuestion(
        id="ic_q1",
        question="Where is the Engine class actually defined? (app.py imports it from core)",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "core/engine.py", "symbol": "Engine", "kind": "class"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="ic_q2",
        question="Trace the import of Config in app.py back to its source definition",
        workflow_type="IMPORT_TRACING",
        expected={"import_chain": ["app.py", "core/__init__.py", "core/config.py"], "final_file": "core/config.py"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Aliased imports --
    files["adapters/__init__.py"] = ""
    files["adapters/http_adapter.py"] = (
        '"""HTTP adapter with aliased imports."""\n\n'
        'from core.engine import Engine as CoreEngine\n'
        'from core.config import Config as AppConfig\n\n\n'
        'class HttpAdapter:\n'
        '    """Wraps the core engine for HTTP access."""\n\n'
        '    def __init__(self):\n'
        '        self.engine = CoreEngine(AppConfig(port=9090))\n\n'
        '    def handle_request(self, path: str) -> dict:\n'
        '        return {"path": path, "engine_running": self.engine._running}\n'
    )

    questions.append(GroundTruthQuestion(
        id="ic_q3",
        question="In http_adapter.py, what does CoreEngine refer to? Where is it defined?",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "core/engine.py", "symbol": "Engine", "alias": "CoreEngine"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Relative imports within a deeper package --
    files["plugins/__init__.py"] = (
        '"""Plugin subsystem."""\n\n'
        'from .base import BasePlugin\n'
        'from .loader import load_plugins\n'
    )
    files["plugins/base.py"] = (
        '"""Base plugin interface."""\n\n\n'
        'class BasePlugin:\n'
        '    """All plugins must extend this class."""\n\n'
        '    name: str = "unnamed"\n\n'
        '    def activate(self):\n'
        '        raise NotImplementedError\n\n'
        '    def deactivate(self):\n'
        '        pass\n'
    )
    files["plugins/loader.py"] = (
        '"""Plugin discovery and loading."""\n\n'
        'from .base import BasePlugin\n\n\n'
        'def load_plugins(directory: str) -> list[BasePlugin]:\n'
        '    """Scan a directory for plugin modules and instantiate them."""\n'
        '    return []  # placeholder\n'
    )
    files["plugins/contrib/__init__.py"] = ""
    files["plugins/contrib/logging_plugin.py"] = (
        '"""Logging plugin using relative imports."""\n\n'
        'from ..base import BasePlugin\n\n\n'
        'class LoggingPlugin(BasePlugin):\n'
        '    """Plugin that logs engine events."""\n\n'
        '    name = "logging"\n\n'
        '    def activate(self):\n'
        '        print(f"[{self.name}] activated")\n'
    )

    questions.append(GroundTruthQuestion(
        id="ic_q4",
        question="In logging_plugin.py, the relative import `from ..base import BasePlugin` -- where does BasePlugin come from?",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "plugins/base.py", "symbol": "BasePlugin"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Circular import resolved at function level --
    files["circular/__init__.py"] = ""
    files["circular/module_a.py"] = (
        '"""Module A -- has a circular dependency with module B."""\n\n'
        'VALUE_A = "alpha"\n\n\n'
        'def get_combined():\n'
        '    """Gets data from module B (import deferred to avoid circular import)."""\n'
        '    from .module_b import VALUE_B\n'
        '    return f"{VALUE_A}-{VALUE_B}"\n'
    )
    files["circular/module_b.py"] = (
        '"""Module B -- has a circular dependency with module A."""\n\n'
        'VALUE_B = "beta"\n\n\n'
        'def get_reversed():\n'
        '    """Gets data from module A (import deferred to avoid circular import)."""\n'
        '    from .module_a import VALUE_A\n'
        '    return f"{VALUE_B}-{VALUE_A}"\n'
    )

    questions.append(GroundTruthQuestion(
        id="ic_q5",
        question="module_a.py and module_b.py have circular imports. How is the cycle resolved?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "files": ["circular/module_a.py", "circular/module_b.py"],
            "keywords": ["circular", "deferred", "function", "import"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.HARD,
    ))

    # -- Scale up for larger tiers --
    _scale = {SizeTier.XS: 0, SizeTier.S: 3, SizeTier.M: 15, SizeTier.L: 50, SizeTier.XL: 150}
    extra_count = _scale[size]
    target_lines = {SizeTier.XS: 15, SizeTier.S: 30, SizeTier.M: 50, SizeTier.L: 70, SizeTier.XL: 60}[size]

    for i in range(extra_count):
        pkg = f"ext_{i // 10:02d}"
        files[f"{pkg}/__init__.py"] = files.get(f"{pkg}/__init__.py", "")
        mod_name = f"handler_{i:03d}"
        src = (
            f'"""Handler module {i}."""\n\n'
            f'from core.config import Config\n\n\n'
            f'class Handler{i}:\n'
            f'    def __init__(self, cfg: Config):\n'
            f'        self.cfg = cfg\n\n'
            f'    def handle(self, data):\n'
            f'        return {{"handler": {i}, "data": data}}\n'
        )
        src = _pad_with_helpers(src, target_lines, f"h{i}")
        files[f"{pkg}/{mod_name}.py"] = src

    questions.append(GroundTruthQuestion(
        id="ic_q6",
        question="Which files directly import from core/config.py?",
        workflow_type="REVERSE_IMPORT_TRACING",
        expected={
            "must_include": ["core/engine.py", "adapters/http_adapter.py"],
        },
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    return SyntheticRepo(
        repo_id=f"import_chains_{size.value}",
        challenge="import_chains",
        size_tier=size,
        files=files,
        questions=questions,
        description="Tests import tracing through re-exports, aliases, relative imports, and circular dependencies",
    )
