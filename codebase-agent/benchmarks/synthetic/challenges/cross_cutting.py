"""Cross-cutting challenge: decorators, dynamic dispatch, plugin patterns.

Tests the agent's ability to follow execution paths through decorators,
registry patterns, and dynamic dispatch -- cases where static call graph
analysis alone is insufficient.
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
    # Pattern 1: Decorator-based route registration
    # ===========================================================
    files["framework/__init__.py"] = ""
    files["framework/router.py"] = (
        '"""Minimal router with decorator-based route registration."""\n\n\n'
        '_ROUTES: dict[str, callable] = {}\n\n\n'
        'def route(path: str):\n'
        '    """Decorator to register a function as a route handler."""\n'
        '    def decorator(func):\n'
        '        _ROUTES[path] = func\n'
        '        return func\n'
        '    return decorator\n\n\n'
        'def dispatch(path: str, **kwargs):\n'
        '    """Dispatch a request to the registered handler."""\n'
        '    handler = _ROUTES.get(path)\n'
        '    if handler is None:\n'
        '        return {"error": "not found", "path": path}\n'
        '    return handler(**kwargs)\n\n\n'
        'def list_routes() -> list[str]:\n'
        '    return list(_ROUTES.keys())\n'
    )

    files["routes/__init__.py"] = ""
    files["routes/users.py"] = (
        '"""User routes -- registered via @route decorator."""\n\n'
        'from framework.router import route\n\n\n'
        '@route("/users")\n'
        'def list_users():\n'
        '    return {"users": ["alice", "bob"]}\n\n\n'
        '@route("/users/create")\n'
        'def create_user(name: str = ""):\n'
        '    return {"created": name}\n'
    )
    files["routes/products.py"] = (
        '"""Product routes -- registered via @route decorator."""\n\n'
        'from framework.router import route\n\n\n'
        '@route("/products")\n'
        'def list_products():\n'
        '    return {"products": ["widget", "gadget"]}\n\n\n'
        '@route("/products/search")\n'
        'def search_products(query: str = ""):\n'
        '    return {"query": query, "results": []}\n'
    )
    files["routes/orders.py"] = (
        '"""Order routes -- registered via @route decorator."""\n\n'
        'from framework.router import route\n\n\n'
        '@route("/orders")\n'
        'def list_orders():\n'
        '    return {"orders": []}\n\n\n'
        '@route("/orders/create")\n'
        'def create_order(user_id: str = "", items: list = None):\n'
        '    return {"user_id": user_id, "items": items or []}\n'
    )

    questions.append(GroundTruthQuestion(
        id="cc_q1",
        question='Which function handles the route "/users/create"?',
        workflow_type="FEATURE_EXPLANATION",
        expected={"file": "routes/users.py", "symbol": "create_user", "route": "/users/create"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="cc_q2",
        question="What routes are registered in the application and where are their handlers?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "routes": {
                "/users": "routes/users.py",
                "/users/create": "routes/users.py",
                "/products": "routes/products.py",
                "/products/search": "routes/products.py",
                "/orders": "routes/orders.py",
                "/orders/create": "routes/orders.py",
            },
            "keywords": ["route", "decorator", "register"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.HARD,
    ))

    # ===========================================================
    # Pattern 2: Plugin registry with dynamic loading
    # ===========================================================
    files["plugins/__init__.py"] = ""
    files["plugins/registry.py"] = (
        '"""Plugin registry -- plugins register themselves on import."""\n\n\n'
        '_PLUGINS: dict[str, type] = {}\n\n\n'
        'def register_plugin(name: str):\n'
        '    """Class decorator to register a plugin."""\n'
        '    def decorator(cls):\n'
        '        _PLUGINS[name] = cls\n'
        '        return cls\n'
        '    return decorator\n\n\n'
        'def get_plugin(name: str):\n'
        '    cls = _PLUGINS.get(name)\n'
        '    if cls is None:\n'
        '        raise KeyError(f"Plugin {name!r} not found")\n'
        '    return cls()\n\n\n'
        'def list_plugins() -> list[str]:\n'
        '    return list(_PLUGINS.keys())\n'
    )
    files["plugins/json_plugin.py"] = (
        '"""JSON serialization plugin."""\n\n'
        'from .registry import register_plugin\n\n\n'
        '@register_plugin("json")\n'
        'class JsonPlugin:\n'
        '    def serialize(self, data) -> str:\n'
        '        import json\n'
        '        return json.dumps(data)\n\n'
        '    def deserialize(self, text: str):\n'
        '        import json\n'
        '        return json.loads(text)\n'
    )
    files["plugins/csv_plugin.py"] = (
        '"""CSV serialization plugin."""\n\n'
        'from .registry import register_plugin\n\n\n'
        '@register_plugin("csv")\n'
        'class CsvPlugin:\n'
        '    def serialize(self, data: list[dict]) -> str:\n'
        '        if not data:\n'
        '            return ""\n'
        '        headers = list(data[0].keys())\n'
        '        lines = [",".join(headers)]\n'
        '        for row in data:\n'
        '            lines.append(",".join(str(row.get(h, "")) for h in headers))\n'
        '        return "\\n".join(lines)\n'
    )

    questions.append(GroundTruthQuestion(
        id="cc_q3",
        question='What class is registered as the "json" plugin?',
        workflow_type="FEATURE_EXPLANATION",
        expected={"file": "plugins/json_plugin.py", "symbol": "JsonPlugin", "plugin_name": "json"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="cc_q4",
        question="How does the plugin system work? How are plugins registered and retrieved?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "registry_file": "plugins/registry.py",
            "keywords": ["decorator", "register", "_PLUGINS", "get_plugin"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))

    # ===========================================================
    # Pattern 3: String-based dispatch / getattr
    # ===========================================================
    files["dispatcher.py"] = (
        '"""Dynamic dispatcher using getattr for string-based routing."""\n\n'
        'import importlib\n\n\n'
        'def dynamic_dispatch(module_name: str, func_name: str, *args, **kwargs):\n'
        '    """Call a function by name from a module by name."""\n'
        '    mod = importlib.import_module(module_name)\n'
        '    func = getattr(mod, func_name)\n'
        '    return func(*args, **kwargs)\n\n\n'
        'COMMAND_MAP = {\n'
        '    "list_users": ("routes.users", "list_users"),\n'
        '    "list_products": ("routes.products", "list_products"),\n'
        '    "list_orders": ("routes.orders", "list_orders"),\n'
        '}\n\n\n'
        'def execute_command(command: str, **kwargs):\n'
        '    """Execute a named command via dynamic dispatch."""\n'
        '    entry = COMMAND_MAP.get(command)\n'
        '    if entry is None:\n'
        '        raise ValueError(f"Unknown command: {command}")\n'
        '    module_name, func_name = entry\n'
        '    return dynamic_dispatch(module_name, func_name, **kwargs)\n'
    )

    questions.append(GroundTruthQuestion(
        id="cc_q5",
        question='When execute_command("list_users") is called, which function actually runs?',
        workflow_type="CALL_GRAPH",
        expected={
            "dispatch_file": "dispatcher.py",
            "target_file": "routes/users.py",
            "target_symbol": "list_users",
            "keywords": ["dynamic", "dispatch", "getattr", "importlib"],
        },
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))

    # -- Entry point --
    files["app.py"] = (
        '"""Application entry point."""\n\n'
        'from framework.router import dispatch, list_routes\n'
        'import routes.users  # noqa: F401  -- triggers registration\n'
        'import routes.products  # noqa: F401\n'
        'import routes.orders  # noqa: F401\n'
        'import plugins.json_plugin  # noqa: F401\n'
        'import plugins.csv_plugin  # noqa: F401\n\n\n'
        'def run():\n'
        '    print("Routes:", list_routes())\n'
        '    result = dispatch("/users")\n'
        '    print("Users:", result)\n\n\n'
        'if __name__ == "__main__":\n'
        '    run()\n'
    )

    questions.append(GroundTruthQuestion(
        id="cc_q6",
        question="Why does app.py import routes.users even though it doesn't use any name from it?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "reason": "side-effect import triggers @route decorator registration",
            "keywords": ["side effect", "register", "decorator", "import"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.HARD,
    ))

    # -- Scale up --
    _extra = {SizeTier.XS: 0, SizeTier.S: 2, SizeTier.M: 12, SizeTier.L: 40, SizeTier.XL: 130}
    for i in range(_extra[size]):
        fname = f"routes/auto_{i:03d}.py"
        src = (
            f'"""Auto-generated route module {i}."""\n\n'
            f'from framework.router import route\n\n\n'
            f'@route("/auto/{i}")\n'
            f'def auto_handler_{i}():\n'
            f'    return {{"auto": {i}}}\n'
        )
        src = _pad_with_helpers(src, target_lines, f"auto{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"cross_cutting_{size.value}",
        challenge="cross_cutting",
        size_tier=size,
        files=files,
        questions=questions,
        description="Decorator registration, plugin systems, and dynamic dispatch patterns",
    )
