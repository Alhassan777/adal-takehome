"""Test mapping challenge: various test file layouts with known coverage gaps.

Tests the agent's ability to discover which test files cover which source
files, handle different naming and directory conventions, and identify
source files that lack test coverage.
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
    # Source modules
    # ===========================================================
    files["src/__init__.py"] = ""
    files["src/models.py"] = (
        '"""Data models."""\n\n\n'
        'class User:\n'
        '    def __init__(self, name: str, email: str):\n'
        '        self.name = name\n'
        '        self.email = email\n\n'
        '    def display_name(self) -> str:\n'
        '        return self.name.title()\n'
    )
    files["src/auth.py"] = (
        '"""Authentication module."""\n\n'
        'from .models import User\n\n\n'
        'def authenticate(username: str, password: str) -> User | None:\n'
        '    """Authenticate a user by credentials."""\n'
        '    if username == "admin" and password == "secret":\n'
        '        return User(name="admin", email="admin@example.com")\n'
        '    return None\n\n\n'
        'def hash_password(password: str) -> str:\n'
        '    return f"hashed_{password}"\n'
    )
    files["src/orders.py"] = (
        '"""Order processing -- INTENTIONALLY UNTESTED."""\n\n'
        'from .models import User\n\n\n'
        'class Order:\n'
        '    def __init__(self, user: User, items: list):\n'
        '        self.user = user\n'
        '        self.items = items\n\n'
        '    def total(self) -> float:\n'
        '        return sum(item["price"] for item in self.items)\n\n\n'
        'def create_order(user: User, items: list) -> Order:\n'
        '    return Order(user, items)\n'
    )
    files["src/notifications.py"] = (
        '"""Notification sending -- INTENTIONALLY UNTESTED."""\n\n\n'
        'def send_email(to: str, subject: str, body: str) -> bool:\n'
        '    return True\n\n\n'
        'def send_sms(phone: str, message: str) -> bool:\n'
        '    return True\n'
    )
    files["src/utils.py"] = (
        '"""Utility functions."""\n\n\n'
        'def slugify(text: str) -> str:\n'
        '    return text.lower().replace(" ", "-")\n\n\n'
        'def truncate(text: str, length: int = 100) -> str:\n'
        '    if len(text) <= length:\n'
        '        return text\n'
        '    return text[:length] + "..."\n'
    )
    files["src/cache.py"] = (
        '"""Caching module."""\n\n\n'
        '_STORE: dict = {}\n\n\n'
        'def cache_get(key: str):\n'
        '    return _STORE.get(key)\n\n\n'
        'def cache_set(key: str, value):\n'
        '    _STORE[key] = value\n\n\n'
        'def cache_clear():\n'
        '    _STORE.clear()\n'
    )

    # ===========================================================
    # Pattern 1: Co-located tests (test_ prefix in same dir)
    # ===========================================================
    files["src/test_utils.py"] = (
        '"""Tests for utils -- co-located in same directory."""\n\n'
        'from .utils import slugify, truncate\n\n\n'
        'def test_slugify():\n'
        '    assert slugify("Hello World") == "hello-world"\n\n\n'
        'def test_truncate_short():\n'
        '    assert truncate("hi") == "hi"\n\n\n'
        'def test_truncate_long():\n'
        '    result = truncate("a" * 200, 50)\n'
        '    assert len(result) == 53  # 50 + "..."\n'
    )

    # ===========================================================
    # Pattern 2: Separate tests/ tree mirroring source layout
    # ===========================================================
    files["tests/__init__.py"] = ""
    files["tests/test_models.py"] = (
        '"""Tests for src.models."""\n\n'
        'from src.models import User\n\n\n'
        'def test_user_creation():\n'
        '    user = User(name="alice", email="alice@example.com")\n'
        '    assert user.name == "alice"\n\n\n'
        'def test_display_name():\n'
        '    user = User(name="alice bob", email="a@b.com")\n'
        '    assert user.display_name() == "Alice Bob"\n'
    )
    files["tests/test_auth.py"] = (
        '"""Tests for src.auth."""\n\n'
        'from src.auth import authenticate, hash_password\n\n\n'
        'def test_authenticate_success():\n'
        '    user = authenticate("admin", "secret")\n'
        '    assert user is not None\n'
        '    assert user.name == "admin"\n\n\n'
        'def test_authenticate_failure():\n'
        '    assert authenticate("wrong", "wrong") is None\n\n\n'
        'def test_hash_password():\n'
        '    assert hash_password("test") == "hashed_test"\n'
    )
    files["tests/test_cache.py"] = (
        '"""Tests for src.cache."""\n\n'
        'from src.cache import cache_get, cache_set, cache_clear\n\n\n'
        'def test_cache_roundtrip():\n'
        '    cache_set("key1", "value1")\n'
        '    assert cache_get("key1") == "value1"\n\n\n'
        'def test_cache_miss():\n'
        '    assert cache_get("nonexistent") is None\n\n\n'
        'def test_cache_clear():\n'
        '    cache_set("temp", "data")\n'
        '    cache_clear()\n'
        '    assert cache_get("temp") is None\n'
    )

    # ===========================================================
    # Pattern 3: Conftest with shared fixtures
    # ===========================================================
    files["tests/conftest.py"] = (
        '"""Shared test fixtures."""\n\n'
        'import pytest\n'
        'from src.models import User\n\n\n'
        '@pytest.fixture\n'
        'def sample_user():\n'
        '    return User(name="fixture_user", email="fixture@test.com")\n\n\n'
        '@pytest.fixture\n'
        'def admin_user():\n'
        '    return User(name="admin", email="admin@test.com")\n'
    )

    # -- Ground truth: which sources ARE tested, which are NOT --
    tested_sources = ["src/models.py", "src/auth.py", "src/utils.py", "src/cache.py"]
    untested_sources = ["src/orders.py", "src/notifications.py"]
    test_map = {
        "src/models.py": ["tests/test_models.py"],
        "src/auth.py": ["tests/test_auth.py"],
        "src/utils.py": ["src/test_utils.py"],
        "src/cache.py": ["tests/test_cache.py"],
    }

    questions.append(GroundTruthQuestion(
        id="tm_q1",
        question="Which test files cover src/models.py?",
        workflow_type="TEST_DISCOVERY",
        expected={"source": "src/models.py", "test_files": ["tests/test_models.py"]},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.EASY,
    ))
    questions.append(GroundTruthQuestion(
        id="tm_q2",
        question="Which test files cover src/utils.py?",
        workflow_type="TEST_DISCOVERY",
        expected={"source": "src/utils.py", "test_files": ["src/test_utils.py"]},
        scoring=ScoringMethod.FILE_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="tm_q3",
        question="Which source files in src/ have no test coverage?",
        workflow_type="MISSING_TESTS",
        expected={"untested_files": untested_sources},
        scoring=ScoringMethod.SYMBOL_SET_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="tm_q4",
        question="Are there tests for the Order class in src/orders.py?",
        workflow_type="TEST_DISCOVERY",
        expected={"source": "src/orders.py", "test_files": [], "has_tests": False},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="tm_q5",
        question="What does conftest.py provide and which tests use its fixtures?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "file": "tests/conftest.py",
            "fixtures": ["sample_user", "admin_user"],
            "keywords": ["fixture", "User", "pytest"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Scale up --
    _extra_src = {SizeTier.XS: 0, SizeTier.S: 3, SizeTier.M: 12, SizeTier.L: 35, SizeTier.XL: 90}
    _extra_tested_ratio = 0.6  # 60% of extras get tests

    for i in range(_extra_src[size]):
        mod_name = f"feature_{i:03d}"
        files[f"src/{mod_name}.py"] = _pad_with_helpers(
            f'"""Feature module {i}."""\n\n\ndef do_{mod_name}(x):\n    return x * 2\n',
            target_lines, f"feat{i}",
        )

        if i < int(_extra_src[size] * _extra_tested_ratio):
            files[f"tests/test_{mod_name}.py"] = (
                f'"""Tests for {mod_name}."""\n\n'
                f'from src.{mod_name} import do_{mod_name}\n\n\n'
                f'def test_{mod_name}():\n'
                f'    assert do_{mod_name}(5) == 10\n'
            )

    return SyntheticRepo(
        repo_id=f"test_mapping_{size.value}",
        challenge="test_mapping",
        size_tier=size,
        files=files,
        questions=questions,
        description="Various test layouts (co-located, separate tree, conftest) with intentional coverage gaps",
    )
