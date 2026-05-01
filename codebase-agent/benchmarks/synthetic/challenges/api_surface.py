"""API surface challenge: __all__ exports, private naming, re-exported public API.

Tests the agent's ability to determine which symbols are part of a module's
public API using __all__, underscore conventions, and __init__.py re-exports.
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
    # Module with explicit __all__
    # ===========================================================
    files["sdk/__init__.py"] = (
        '"""SDK package -- curated public API via __init__.py."""\n\n'
        'from .client import Client\n'
        'from .models import Request, Response\n'
        'from .auth import authenticate\n\n'
        '__all__ = ["Client", "Request", "Response", "authenticate"]\n'
    )
    files["sdk/client.py"] = (
        '"""SDK client -- public."""\n\n'
        'from .models import Request, Response\n'
        'from ._internal import _build_headers\n\n\n'
        '__all__ = ["Client"]\n\n\n'
        'class Client:\n'
        '    """Public SDK client for making API calls."""\n\n'
        '    def __init__(self, api_key: str):\n'
        '        self.api_key = api_key\n\n'
        '    def send(self, request: Request) -> Response:\n'
        '        headers = _build_headers(self.api_key)\n'
        '        return Response(status=200, body={"ok": True})\n\n\n'
        'class _ClientPool:\n'
        '    """Internal connection pool -- not public."""\n\n'
        '    def __init__(self, size: int = 10):\n'
        '        self._connections = []\n'
        '        self._size = size\n\n'
        '    def acquire(self):\n'
        '        return None\n'
    )
    files["sdk/models.py"] = (
        '"""SDK data models -- public."""\n\n'
        'from dataclasses import dataclass\n\n\n'
        '__all__ = ["Request", "Response"]\n\n\n'
        '@dataclass\n'
        'class Request:\n'
        '    """Public request model."""\n'
        '    method: str\n'
        '    path: str\n'
        '    body: dict | None = None\n\n\n'
        '@dataclass\n'
        'class Response:\n'
        '    """Public response model."""\n'
        '    status: int\n'
        '    body: dict | None = None\n\n\n'
        '@dataclass\n'
        'class _RawResponse:\n'
        '    """Internal raw response -- not public."""\n'
        '    data: bytes = b""\n'
        '    headers: dict | None = None\n'
    )
    files["sdk/auth.py"] = (
        '"""SDK authentication -- partially public."""\n\n\n'
        '__all__ = ["authenticate"]\n\n\n'
        'def authenticate(api_key: str) -> dict:\n'
        '    """Public: validate an API key."""\n'
        '    return {"valid": bool(api_key), "key": api_key[:4] + "..."}\n\n\n'
        'def _refresh_token(token: str) -> str:\n'
        '    """Internal: refresh an auth token."""\n'
        '    return f"refreshed_{token}"\n\n\n'
        'def _validate_signature(payload: str, signature: str) -> bool:\n'
        '    """Internal: validate request signature."""\n'
        '    return len(signature) > 10\n'
    )
    files["sdk/_internal.py"] = (
        '"""Internal utilities -- entirely private module."""\n\n\n'
        'def _build_headers(api_key: str) -> dict:\n'
        '    return {"Authorization": f"Bearer {api_key}"}\n\n\n'
        'def _parse_response(raw: bytes) -> dict:\n'
        '    import json\n'
        '    return json.loads(raw)\n\n\n'
        'def _retry_request(func, max_retries: int = 3):\n'
        '    for attempt in range(max_retries):\n'
        '        try:\n'
        '            return func()\n'
        '        except Exception:\n'
        '            if attempt == max_retries - 1:\n'
        '                raise\n'
    )

    public_symbols = ["Client", "Request", "Response", "authenticate"]
    private_symbols = [
        "_ClientPool", "_RawResponse", "_refresh_token",
        "_validate_signature", "_build_headers", "_parse_response", "_retry_request",
    ]

    questions.append(GroundTruthQuestion(
        id="api_q1",
        question="What is the public API of the sdk/ package?",
        workflow_type="API_SURFACE",
        expected={"public_symbols": public_symbols, "package": "sdk"},
        scoring=ScoringMethod.SYMBOL_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="api_q2",
        question="Which symbols in sdk/client.py are public vs private?",
        workflow_type="API_SURFACE",
        expected={
            "file": "sdk/client.py",
            "public": ["Client"],
            "private": ["_ClientPool"],
        },
        scoring=ScoringMethod.SYMBOL_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="api_q3",
        question="Is _RawResponse part of the public SDK API?",
        workflow_type="API_SURFACE",
        expected={"symbol": "_RawResponse", "is_public": False, "file": "sdk/models.py"},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.EASY,
    ))
    questions.append(GroundTruthQuestion(
        id="api_q4",
        question="Where is authenticate actually defined? (sdk/__init__.py re-exports it)",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "sdk/auth.py", "symbol": "authenticate"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # ===========================================================
    # Second library with only naming conventions (no __all__)
    # ===========================================================
    files["helpers/__init__.py"] = (
        '"""Helper package -- no __all__, public/private by convention."""\n\n'
        'from .strings import capitalize_words, pad_string\n'
        'from .numbers import round_to, clamp\n'
    )
    files["helpers/strings.py"] = (
        '"""String helpers."""\n\n\n'
        'def capitalize_words(text: str) -> str:\n'
        '    """Public: capitalize each word."""\n'
        '    return " ".join(w.capitalize() for w in text.split())\n\n\n'
        'def pad_string(text: str, width: int, char: str = " ") -> str:\n'
        '    """Public: pad a string to a given width."""\n'
        '    return text.center(width, char)\n\n\n'
        'def _normalize_whitespace(text: str) -> str:\n'
        '    """Private: collapse whitespace."""\n'
        '    return " ".join(text.split())\n'
    )
    files["helpers/numbers.py"] = (
        '"""Number helpers."""\n\n\n'
        'def round_to(value: float, decimals: int = 2) -> float:\n'
        '    """Public: round to N decimals."""\n'
        '    return round(value, decimals)\n\n\n'
        'def clamp(value: float, low: float, high: float) -> float:\n'
        '    """Public: clamp between bounds."""\n'
        '    return max(low, min(value, high))\n\n\n'
        'def _is_close(a: float, b: float, tol: float = 1e-9) -> bool:\n'
        '    """Private: approximate equality check."""\n'
        '    return abs(a - b) < tol\n'
    )

    questions.append(GroundTruthQuestion(
        id="api_q5",
        question="What is the public API of the helpers/ package? (no __all__ defined)",
        workflow_type="API_SURFACE",
        expected={
            "public_symbols": ["capitalize_words", "pad_string", "round_to", "clamp"],
            "private_symbols": ["_normalize_whitespace", "_is_close"],
        },
        scoring=ScoringMethod.SYMBOL_SET_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="api_q6",
        question="Give an overview of the sdk/ module -- what does it provide?",
        workflow_type="MODULE_OVERVIEW",
        expected={
            "directory": "sdk",
            "keywords": ["Client", "Request", "Response", "authenticate", "API"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Scale up --
    _extra = {SizeTier.XS: 0, SizeTier.S: 2, SizeTier.M: 15, SizeTier.L: 50, SizeTier.XL: 140}
    for i in range(_extra[size]):
        fname = f"sdk/extensions/ext_{i:03d}.py"
        if "sdk/extensions/__init__.py" not in files:
            files["sdk/extensions/__init__.py"] = ""
        src = (
            f'"""SDK extension {i}."""\n\n\n'
            f'__all__ = ["Extension{i}"]\n\n\n'
            f'class Extension{i}:\n'
            f'    """Public extension."""\n'
            f'    def run(self):\n'
            f'        return {i}\n\n\n'
            f'class _ExtHelper{i}:\n'
            f'    """Private helper."""\n'
            f'    pass\n'
        )
        src = _pad_with_helpers(src, target_lines, f"ext{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"api_surface_{size.value}",
        challenge="api_surface",
        size_tier=size,
        files=files,
        questions=questions,
        description="Public vs private API boundaries via __all__, underscore conventions, and re-exports",
    )
