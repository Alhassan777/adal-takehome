"""Deep hierarchy challenge: deeply nested packages with buried target symbols.

Tests the agent's ability to navigate through many levels of directories,
find symbols in deeply nested locations, and provide correct module overviews
and architecture maps for complex project structures.
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

_DEPTH = {SizeTier.XS: 3, SizeTier.S: 4, SizeTier.M: 5, SizeTier.L: 6, SizeTier.XL: 7}
_BREADTH = {SizeTier.XS: 1, SizeTier.S: 2, SizeTier.M: 3, SizeTier.L: 4, SizeTier.XL: 5}
_LINES = {SizeTier.XS: 15, SizeTier.S: 25, SizeTier.M: 45, SizeTier.L: 65, SizeTier.XL: 55}


def _nested_path(segments: list[str]) -> str:
    return "/".join(segments)


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []

    depth = _DEPTH[size]
    breadth = _BREADTH[size]
    target_lines = _LINES[size]

    # -- Build a tree of nested packages --
    layer_names = ["app", "services", "auth", "providers", "backends", "drivers", "adapters"][:depth]

    # The "needle" -- a specific class buried at maximum depth
    needle_path_parts = list(layer_names)
    needle_dir = "/".join(needle_path_parts)
    needle_file = f"{needle_dir}/oauth_handler.py"

    # Create __init__.py at every level
    for level in range(1, len(layer_names) + 1):
        init_path = "/".join(layer_names[:level]) + "/__init__.py"
        files[init_path] = f'"""Package: {layer_names[level-1]}."""\n'

    # Create the needle file
    needle_src = (
        '"""OAuth authentication handler -- the deeply buried target."""\n\n'
        'from dataclasses import dataclass\n\n\n'
        '@dataclass\n'
        'class OAuthCredentials:\n'
        '    """Stores OAuth provider credentials."""\n\n'
        '    client_id: str\n'
        '    client_secret: str\n'
        '    redirect_uri: str\n\n\n'
        'class OAuthHandler:\n'
        '    """Handles OAuth authentication flow."""\n\n'
        '    def __init__(self, credentials: OAuthCredentials):\n'
        '        self.credentials = credentials\n'
        '        self._token = None\n\n'
        '    def authenticate(self, code: str) -> str:\n'
        '        """Exchange authorization code for access token."""\n'
        '        self._token = f"token_{code}_{self.credentials.client_id}"\n'
        '        return self._token\n\n'
        '    def refresh_token(self) -> str:\n'
        '        """Refresh an expired access token."""\n'
        '        self._token = f"refreshed_{self._token}"\n'
        '        return self._token\n\n'
        '    def revoke(self):\n'
        '        """Revoke the current token."""\n'
        '        self._token = None\n'
    )
    needle_src = _pad_with_helpers(needle_src, target_lines, "oauth")
    files[needle_file] = needle_src

    questions.append(GroundTruthQuestion(
        id="dh_q1",
        question="Where is the OAuthHandler class defined?",
        workflow_type="SYMBOL_LOOKUP",
        expected={"file": needle_file, "symbol": "OAuthHandler", "kind": "class"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="dh_q2",
        question="What is the authenticate method in OAuthHandler and where is it?",
        workflow_type="GOTO_DEFINITION_NO_FILE",
        expected={"file": needle_file, "symbol": "authenticate"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))

    # -- Sibling modules at each depth level --
    sibling_modules = ["session", "token_store", "permissions", "rate_limiter", "audit_log"]

    for level in range(1, len(layer_names)):
        parent = "/".join(layer_names[:level + 1])
        for b in range(min(breadth, len(sibling_modules))):
            mod_name = sibling_modules[b]
            mod_file = f"{parent}/{mod_name}.py"
            src = (
                f'"""Module {mod_name} at level {level}."""\n\n\n'
                f'class {mod_name.title().replace("_", "")}:\n'
                f'    """Handles {mod_name.replace("_", " ")} at the {layer_names[level]} layer."""\n\n'
                f'    def __init__(self):\n'
                f'        self.active = True\n\n'
                f'    def process(self, data):\n'
                f'        return {{"layer": "{layer_names[level]}", "module": "{mod_name}", "data": data}}\n'
            )
            src = _pad_with_helpers(src, target_lines, f"{mod_name[:3]}_{level}")
            files[mod_file] = src

    # -- Top-level entry point that references the deep target --
    files["main.py"] = (
        '"""Application entry point -- imports from the deepest nested module."""\n\n'
        f'from {".".join(layer_names)}.oauth_handler import OAuthHandler, OAuthCredentials\n\n\n'
        'def main():\n'
        '    creds = OAuthCredentials(\n'
        '        client_id="my-app",\n'
        '        client_secret="secret123",\n'
        '        redirect_uri="http://localhost/callback",\n'
        '    )\n'
        '    handler = OAuthHandler(creds)\n'
        '    token = handler.authenticate("auth_code_xyz")\n'
        '    print(f"Got token: {token}")\n\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    )

    questions.append(GroundTruthQuestion(
        id="dh_q3",
        question="Describe the architecture of this project -- what are the nested package layers?",
        workflow_type="ARCHITECTURE_MAP",
        expected={"layers": layer_names, "deepest_file": needle_file},
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="dh_q4",
        question=f"Give an overview of the {layer_names[1]}/ package",
        workflow_type="MODULE_OVERVIEW",
        expected={
            "directory": "/".join(layer_names[:2]),
            "contains_packages": True,
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Extra top-level filler for larger sizes --
    _extra = {SizeTier.XS: 0, SizeTier.S: 3, SizeTier.M: 10, SizeTier.L: 40, SizeTier.XL: 120}
    for i in range(_extra[size]):
        fname = f"lib/component_{i:03d}.py"
        if "lib/__init__.py" not in files:
            files["lib/__init__.py"] = ""
        src = (
            f'"""Component {i}."""\n\n\n'
            f'def execute_{i}(params):\n'
            f'    return {{"component": {i}, "params": params}}\n'
        )
        src = _pad_with_helpers(src, target_lines, f"comp{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"deep_hierarchy_{size.value}",
        challenge="deep_hierarchy",
        size_tier=size,
        files=files,
        questions=questions,
        description="Deeply nested package structure to test navigation depth and architecture mapping",
    )
