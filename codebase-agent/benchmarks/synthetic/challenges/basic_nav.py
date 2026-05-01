"""Basic navigation challenge: symbol lookup, file reading, text search.

Generates flat Python projects with clear function/class names at various sizes.
Tests the agent's ability to find symbols, read files, and search text -- the
foundation that all other workflows build on.
"""

from __future__ import annotations

from ..generator import (
    Difficulty,
    GroundTruthQuestion,
    ScoringMethod,
    SizeTier,
    SyntheticRepo,
    _make_class,
    _make_function,
    _pad_with_helpers,
)

_FILE_COUNTS = {SizeTier.XS: 4, SizeTier.S: 12, SizeTier.M: 35, SizeTier.L: 90, SizeTier.XL: 210}
_LINES_PER_FILE = {SizeTier.XS: 20, SizeTier.S: 35, SizeTier.M: 60, SizeTier.L: 80, SizeTier.XL: 70}


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []

    n_files = _FILE_COUNTS[size]
    target_lines = _LINES_PER_FILE[size]

    # -- models.py: always present, contains core data classes --
    models_src = (
        '"""Data models for the order processing system."""\n\n'
        'from dataclasses import dataclass\n\n\n'
        '@dataclass\n'
        'class Order:\n'
        '    """Represents a customer order."""\n\n'
        '    order_id: str\n'
        '    customer_name: str\n'
        '    total: float\n'
        '    status: str = "pending"\n\n\n'
        '@dataclass\n'
        'class Product:\n'
        '    """Represents a product in the catalog."""\n\n'
        '    sku: str\n'
        '    name: str\n'
        '    price: float\n'
        '    stock: int = 0\n'
    )
    models_src = _pad_with_helpers(models_src, target_lines, "model_util")
    files["models.py"] = models_src

    questions.append(GroundTruthQuestion(
        id="bn_q1",
        question="Where is the Order class defined?",
        workflow_type="SYMBOL_LOOKUP",
        expected={"file": "models.py", "symbol": "Order", "kind": "class"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- services.py: business logic that imports models --
    services_src = (
        '"""Order processing business logic."""\n\n'
        'from models import Order, Product\n\n\n'
        'def process_order(order: Order) -> dict:\n'
        '    """Validate and process a customer order."""\n'
        '    if order.total <= 0:\n'
        '        raise ValueError("Order total must be positive")\n'
        '    return {"order_id": order.order_id, "status": "processed"}\n\n\n'
        'def calculate_discount(order: Order, rate: float) -> float:\n'
        '    """Apply a discount rate to an order total."""\n'
        '    return round(order.total * (1 - rate), 2)\n\n\n'
        'def check_inventory(product: Product, quantity: int) -> bool:\n'
        '    """Check whether enough stock exists for the requested quantity."""\n'
        '    return product.stock >= quantity\n'
    )
    services_src = _pad_with_helpers(services_src, target_lines, "svc_util")
    files["services.py"] = services_src

    questions.append(GroundTruthQuestion(
        id="bn_q2",
        question="Where is process_order defined?",
        workflow_type="SYMBOL_LOOKUP",
        expected={"file": "services.py", "symbol": "process_order", "kind": "function"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.EASY,
    ))
    questions.append(GroundTruthQuestion(
        id="bn_q3",
        question="Which files import from models.py?",
        workflow_type="REVERSE_IMPORT_TRACING",
        expected={"files": ["services.py"]},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- utils.py: shared utilities --
    utils_src = (
        '"""Shared utility functions."""\n\n\n'
        'def format_currency(amount: float) -> str:\n'
        '    """Format a float as a USD currency string."""\n'
        '    return f"${amount:,.2f}"\n\n\n'
        'def slugify(text: str) -> str:\n'
        '    """Convert text to a URL-friendly slug."""\n'
        '    return text.lower().strip().replace(" ", "-")\n\n\n'
        'def clamp(value: float, low: float, high: float) -> float:\n'
        '    """Clamp a value between low and high bounds."""\n'
        '    return max(low, min(value, high))\n'
    )
    utils_src = _pad_with_helpers(utils_src, target_lines, "util")
    files["utils.py"] = utils_src

    questions.append(GroundTruthQuestion(
        id="bn_q4",
        question='Search for the text "currency" in the codebase',
        workflow_type="TEXT_SEARCH",
        expected={"files": ["utils.py"], "keyword": "currency"},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- main.py: entry point --
    main_src = (
        '"""Application entry point."""\n\n'
        'from models import Order\n'
        'from services import process_order, calculate_discount\n'
        'from utils import format_currency\n\n\n'
        'def main():\n'
        '    """Run the order processing pipeline."""\n'
        '    order = Order(order_id="ORD-001", customer_name="Alice", total=99.99)\n'
        '    result = process_order(order)\n'
        '    discounted = calculate_discount(order, 0.1)\n'
        '    print(f"Processed {result[\'order_id\']}: {format_currency(discounted)}")\n\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    )
    main_src = _pad_with_helpers(main_src, target_lines, "main_util")
    files["main.py"] = main_src

    questions.append(GroundTruthQuestion(
        id="bn_q5",
        question="What does main.py import?",
        workflow_type="IMPORT_TRACING",
        expected={"imports_from": ["models", "services", "utils"]},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- Scale up: add more modules for larger tiers --
    extra_modules = [
        ("validators.py", "validators", "Validation logic",
         [("validate_email", "email: str", 'return "@" in email and "." in email', "Check email format"),
          ("validate_phone", "phone: str", 'return len(phone) >= 10 and phone.replace("-", "").isdigit()', "Check phone format"),
          ("validate_sku", "sku: str", 'return sku.startswith("SKU-") and len(sku) == 10', "Validate product SKU format")]),
        ("formatters.py", "formatters", "Output formatting",
         [("format_table", "rows: list, headers: list", 'return "\\n".join([" | ".join(headers)] + [" | ".join(str(c) for c in r) for r in rows])', "Format data as ASCII table"),
          ("format_json", "data: dict", 'import json\nreturn json.dumps(data, indent=2)', "Pretty-print JSON")]),
        ("config.py", "config", "Application configuration",
         [("load_config", "path: str", 'return {"debug": False, "port": 8080}', "Load config from file"),
          ("get_setting", "key: str, default=None", 'cfg = load_config("")\nreturn cfg.get(key, default)', "Get a single config value")]),
        ("database.py", "database", "Database access layer",
         [("connect", "dsn: str", 'return {"connection": dsn, "active": True}', "Establish database connection"),
          ("execute_query", "conn: dict, query: str", 'return [{"id": 1}]', "Execute a SQL query"),
          ("close_connection", "conn: dict", 'conn["active"] = False', "Close database connection")]),
        ("auth.py", "auth", "Authentication module",
         [("hash_password", "password: str", 'return f"hashed_{password}"', "Hash a plaintext password"),
          ("verify_password", "password: str, hashed: str", 'return hashed == f"hashed_{password}"', "Verify a password against its hash"),
          ("create_token", "user_id: str", 'return f"token_{user_id}"', "Create an authentication token")]),
        ("notifications.py", "notifications", "Notification dispatching",
         [("send_email", "to: str, subject: str, body: str", 'return {"sent": True, "to": to}', "Send email notification"),
          ("send_sms", "phone: str, message: str", 'return {"sent": True, "phone": phone}', "Send SMS notification")]),
        ("cache.py", "cache", "In-memory caching",
         [("get_cache", "key: str", '_CACHE = {}\nreturn _CACHE.get(key)', "Retrieve a cached value"),
          ("set_cache", "key: str, value, ttl: int = 300", '_CACHE = {}\n_CACHE[key] = value', "Store a value in cache"),
          ("clear_cache", "", '_CACHE = {}', "Clear the entire cache")]),
        ("logging_utils.py", "logging_utils", "Structured logging helpers",
         [("get_logger", "name: str", 'import logging\nreturn logging.getLogger(name)', "Get a named logger"),
          ("log_event", "logger, event: str, **kwargs", 'logger.info(f"{event}: {kwargs}")', "Log a structured event")]),
    ]

    added = 4  # models, services, utils, main
    importers = ["services.py"]  # track files that import models for q3

    for mod_file, mod_name, mod_doc, funcs in extra_modules:
        if added >= n_files:
            break
        src_lines = [f'"""{mod_doc}."""\n']
        for fname, params, body, fdoc in funcs:
            src_lines.append(f"\n\ndef {fname}({params}):")
            src_lines.append(f'    """{fdoc}."""')
            for bline in body.split("\n"):
                src_lines.append(f"    {bline}")
            src_lines.append("")
        src = "\n".join(src_lines)
        src = _pad_with_helpers(src, target_lines, mod_name[:4])
        files[mod_file] = src
        added += 1

    # For M/L/XL: generate numbered filler modules under a package
    if added < n_files:
        files["extras/__init__.py"] = ""
        added += 1
        filler_idx = 0
        while added < n_files:
            fname = f"extras/module_{filler_idx:03d}.py"
            src = (
                f'"""Auto-generated module {filler_idx} for scaling tests."""\n\n\n'
                f'MAGIC_NUMBER_{filler_idx} = {filler_idx * 42}\n\n\n'
                f'def compute_{filler_idx}(x):\n'
                f'    """Compute result for module {filler_idx}."""\n'
                f'    return x + MAGIC_NUMBER_{filler_idx}\n\n\n'
                f'class Processor{filler_idx}:\n'
                f'    """Processor for batch {filler_idx}."""\n\n'
                f'    def run(self, data):\n'
                f'        return [compute_{filler_idx}(item) for item in data]\n'
            )
            src = _pad_with_helpers(src, target_lines, f"fill{filler_idx}")
            files[fname] = src
            added += 1
            filler_idx += 1

    questions.append(GroundTruthQuestion(
        id="bn_q6",
        question="List all Python files in the project",
        workflow_type="FILE_LISTING",
        expected={"file_count": len(files)},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.EASY,
    ))

    if size.value in ("M", "L", "XL"):
        questions.append(GroundTruthQuestion(
            id="bn_q7",
            question="Where is the validate_email function defined?",
            workflow_type="SYMBOL_LOOKUP",
            expected={"file": "validators.py", "symbol": "validate_email", "kind": "function"},
            scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
            difficulty=Difficulty.EASY,
        ))
        questions.append(GroundTruthQuestion(
            id="bn_q8",
            question="Where is the connect function for the database defined?",
            workflow_type="SYMBOL_LOOKUP",
            expected={"file": "database.py", "symbol": "connect", "kind": "function"},
            scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
            difficulty=Difficulty.MEDIUM,
        ))

    return SyntheticRepo(
        repo_id=f"basic_nav_{size.value}",
        challenge="basic_nav",
        size_tier=size,
        files=files,
        questions=questions,
        description="Flat Python project for testing basic symbol lookup, file listing, and text search",
    )
