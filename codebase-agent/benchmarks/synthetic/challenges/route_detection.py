"""Route detection challenge: FastAPI / Flask-style route decorator extraction.

Tests the agent's ability to detect HTTP route decorators, count endpoints,
identify which files define API handlers, and distinguish route files from
plain utility modules.
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

_LINES = {SizeTier.XS: 20, SizeTier.S: 30, SizeTier.M: 50, SizeTier.L: 70, SizeTier.XL: 60}


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []
    target_lines = _LINES[size]

    # ===========================================================
    # 1) Main API file with @app.* CRUD endpoints
    # ===========================================================
    files["api/__init__.py"] = ""
    files["api/users.py"] = (
        '"""User CRUD endpoints."""\n\n'
        'from fastapi import FastAPI\n\n'
        'app = FastAPI()\n\n\n'
        '@app.get("/users")\n'
        'def list_users():\n'
        '    """List all users."""\n'
        '    return []\n\n\n'
        '@app.post("/users")\n'
        'def create_user(data: dict):\n'
        '    """Create a user."""\n'
        '    return {"id": 1, **data}\n\n\n'
        '@app.get("/users/{user_id}")\n'
        'def get_user(user_id: int):\n'
        '    """Get a single user by ID."""\n'
        '    return {"id": user_id}\n\n\n'
        '@app.put("/users/{user_id}")\n'
        'def update_user(user_id: int, data: dict):\n'
        '    """Update a user."""\n'
        '    return {"id": user_id, **data}\n\n\n'
        '@app.delete("/users/{user_id}")\n'
        'def delete_user(user_id: int):\n'
        '    """Delete a user."""\n'
        '    return {"deleted": True}\n'
    )

    # ===========================================================
    # 2) Sub-router file with @router.* decorators
    # ===========================================================
    files["api/orders.py"] = (
        '"""Order endpoints using a sub-router."""\n\n'
        'from fastapi import APIRouter\n\n'
        'router = APIRouter(prefix="/orders")\n\n\n'
        '@router.get("/")\n'
        'def list_orders():\n'
        '    """List all orders."""\n'
        '    return []\n\n\n'
        '@router.post("/")\n'
        'def create_order(data: dict):\n'
        '    """Create an order."""\n'
        '    return {"order_id": 1}\n\n\n'
        '@router.get("/{order_id}")\n'
        'def get_order(order_id: int):\n'
        '    """Get order by ID."""\n'
        '    return {"order_id": order_id}\n'
    )

    # ===========================================================
    # 3) Mixed file: routes + a class
    # ===========================================================
    files["api/products.py"] = (
        '"""Product endpoints with a service class."""\n\n'
        'from fastapi import APIRouter\n\n'
        'router = APIRouter(prefix="/products")\n\n\n'
        'class ProductService:\n'
        '    """Business logic for products."""\n\n'
        '    def __init__(self):\n'
        '        self.db = []\n\n'
        '    def find_all(self):\n'
        '        return self.db\n\n\n'
        '_svc = ProductService()\n\n\n'
        '@router.get("/")\n'
        'def list_products():\n'
        '    """List products."""\n'
        '    return _svc.find_all()\n\n\n'
        '@router.post("/")\n'
        'def create_product(data: dict):\n'
        '    """Create a product."""\n'
        '    _svc.db.append(data)\n'
        '    return data\n'
    )

    # ===========================================================
    # 4) Plain utility file -- no decorators (negative case)
    # ===========================================================
    files["utils/__init__.py"] = ""
    files["utils/helpers.py"] = (
        '"""General utility functions -- no routes."""\n\n\n'
        'def slugify(text: str) -> str:\n'
        '    """Convert text to a URL-safe slug."""\n'
        '    return text.lower().replace(" ", "-")\n\n\n'
        'def paginate(items: list, page: int = 1, per_page: int = 20) -> list:\n'
        '    """Return a single page of items."""\n'
        '    start = (page - 1) * per_page\n'
        '    return items[start : start + per_page]\n\n\n'
        'def format_currency(amount: float, symbol: str = "$") -> str:\n'
        '    """Format a number as currency."""\n'
        '    return f"{symbol}{amount:,.2f}"\n'
    )

    # ===========================================================
    # Ground truth questions
    # ===========================================================
    questions.append(GroundTruthQuestion(
        id="route_q1",
        question="How many API endpoints does api/users.py define?",
        workflow_type="ROUTE_DETECTION",
        expected={"file": "api/users.py", "count": 5, "answer": True},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.EASY,
    ))
    questions.append(GroundTruthQuestion(
        id="route_q2",
        question="Which files define HTTP route handlers?",
        workflow_type="ROUTE_DETECTION",
        expected={"files": ["api/users.py", "api/orders.py", "api/products.py"]},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="route_q3",
        question="Give an overview of the api/ directory.",
        workflow_type="MODULE_OVERVIEW",
        expected={
            "directory": "api",
            "keywords": ["endpoint", "route", "API"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="route_q4",
        question="What routes does api/orders.py define?",
        workflow_type="ROUTE_DETECTION",
        expected={
            "file": "api/orders.py",
            "keywords": ["/", "order"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="route_q5",
        question="Does utils/helpers.py define any API endpoints?",
        workflow_type="ROUTE_DETECTION",
        expected={"file": "utils/helpers.py", "answer": False},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.EASY,
    ))

    # -- Scale up --
    _extra = {SizeTier.XS: 0, SizeTier.S: 3, SizeTier.M: 20, SizeTier.L: 60, SizeTier.XL: 150}
    for i in range(_extra[size]):
        fname = f"api/ext/resource_{i:03d}.py"
        if "api/ext/__init__.py" not in files:
            files["api/ext/__init__.py"] = ""
        src = (
            f'"""Auto-generated resource {i} endpoints."""\n\n'
            f'from fastapi import APIRouter\n\n'
            f'router_{i} = APIRouter(prefix="/resource{i}")\n\n\n'
            f'@router_{i}.get("/")\n'
            f'def list_resource_{i}():\n'
            f'    return []\n\n\n'
            f'@router_{i}.post("/")\n'
            f'def create_resource_{i}(data: dict):\n'
            f'    return data\n'
        )
        src = _pad_with_helpers(src, target_lines, f"res{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"route_detection_{size.value}",
        challenge="route_detection",
        size_tier=size,
        files=files,
        questions=questions,
        description="HTTP route decorator detection for FastAPI-style CRUD endpoints",
    )
