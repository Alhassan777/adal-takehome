"""Name collision challenge: same symbol names appearing in multiple files.

Tests the agent's 5-phase symbol disambiguation -- when a user asks "where is
Handler defined?" and there are 5+ classes named Handler in different modules,
the agent must use context clues (imports, package structure, expected kind)
to resolve to the correct one.
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

_COLLISION_COUNT = {SizeTier.XS: 3, SizeTier.S: 5, SizeTier.M: 8, SizeTier.L: 15, SizeTier.XL: 25}
_LINES = {SizeTier.XS: 18, SizeTier.S: 30, SizeTier.M: 50, SizeTier.L: 65, SizeTier.XL: 55}


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []

    n = _COLLISION_COUNT[size]
    target_lines = _LINES[size]

    # -- Create N modules each containing a class named "Handler" --
    domains = [
        ("http", "Handles incoming HTTP requests and routing"),
        ("websocket", "Manages WebSocket connection lifecycle"),
        ("grpc", "Processes gRPC service calls"),
        ("events", "Dispatches domain events to subscribers"),
        ("queue", "Consumes messages from the task queue"),
        ("email", "Sends and templates email messages"),
        ("webhook", "Receives and validates incoming webhooks"),
        ("file", "Manages file upload and download operations"),
        ("auth", "Handles authentication and token validation"),
        ("payment", "Processes payment transactions"),
        ("notification", "Routes notifications to channels"),
        ("search", "Handles search query execution"),
        ("cache", "Manages cache read and write operations"),
        ("logging", "Handles structured log collection"),
        ("metrics", "Collects and exports application metrics"),
        ("rate_limit", "Enforces request rate limiting"),
        ("retry", "Manages retry logic for failed operations"),
        ("transform", "Applies data transformations"),
        ("validate", "Validates incoming data payloads"),
        ("schedule", "Handles scheduled task execution"),
        ("stream", "Processes streaming data pipelines"),
        ("compress", "Handles data compression operations"),
        ("encrypt", "Manages encryption and decryption"),
        ("migrate", "Handles database migration execution"),
        ("backup", "Manages data backup operations"),
    ]

    handler_files = []
    for i in range(n):
        domain, doc = domains[i]
        pkg = f"handlers/{domain}"
        files[f"handlers/__init__.py"] = files.get("handlers/__init__.py", "")
        files[f"{pkg}/__init__.py"] = ""

        # Each module has a class named "Handler" with a domain-specific method
        src = (
            f'"""{doc}."""\n\n\n'
            f'class Handler:\n'
            f'    """{doc}."""\n\n'
            f'    protocol = "{domain}"\n\n'
            f'    def __init__(self):\n'
            f'        self.active = True\n'
            f'        self._count = 0\n\n'
            f'    def handle(self, request):\n'
            f'        """Process an incoming {domain} request."""\n'
            f'        self._count += 1\n'
            f'        return {{"protocol": self.protocol, "count": self._count, "request": request}}\n\n'
            f'    def shutdown(self):\n'
            f'        self.active = False\n'
        )
        src = _pad_with_helpers(src, target_lines, f"{domain[:4]}")
        mod_file = f"{pkg}/handler.py"
        files[mod_file] = src
        handler_files.append(mod_file)

    # -- A function named "validate" in EACH handler module --
    for i in range(n):
        domain = domains[i][0]
        pkg = f"handlers/{domain}"
        validate_src = (
            f'"""Validation for {domain} requests."""\n\n\n'
            f'def validate(data: dict) -> bool:\n'
            f'    """Validate a {domain} payload."""\n'
            f'    return bool(data) and "type" in data\n\n\n'
            f'def sanitize(data: dict) -> dict:\n'
            f'    """Sanitize a {domain} payload."""\n'
            f'    return {{k: str(v).strip() for k, v in data.items()}}\n'
        )
        validate_src = _pad_with_helpers(validate_src, target_lines, f"val_{domain[:3]}")
        files[f"{pkg}/validate.py"] = validate_src

    # -- Consumer module that imports from a specific handler --
    files["server.py"] = (
        '"""Main server that uses the HTTP handler."""\n\n'
        'from handlers.http.handler import Handler\n'
        'from handlers.http.validate import validate\n\n\n'
        'def start_server(port: int = 8080):\n'
        '    """Start the HTTP server."""\n'
        '    handler = Handler()\n'
        '    print(f"Starting {handler.protocol} server on port {port}")\n'
        '    return handler\n\n\n'
        'def handle_request(handler: Handler, data: dict):\n'
        '    """Validate and handle a request."""\n'
        '    if not validate(data):\n'
        '        raise ValueError("Invalid request")\n'
        '    return handler.handle(data)\n'
    )

    questions.append(GroundTruthQuestion(
        id="nc_q1",
        question="In server.py, where is the Handler class that it imports actually defined?",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "handlers/http/handler.py", "symbol": "Handler", "context_file": "server.py"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="nc_q2",
        question="Where is the Handler class that handles WebSocket connections?",
        workflow_type="GOTO_DEFINITION_NO_FILE",
        expected={"file": "handlers/websocket/handler.py", "symbol": "Handler"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="nc_q3",
        question="How many files contain a class named Handler?",
        workflow_type="SYMBOL_LOOKUP",
        expected={"symbol": "Handler", "file_count": n, "files": handler_files},
        scoring=ScoringMethod.BOOLEAN_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))
    questions.append(GroundTruthQuestion(
        id="nc_q4",
        question="Where is the validate function used in server.py defined?",
        workflow_type="GOTO_DEFINITION_HINT",
        expected={"file": "handlers/http/validate.py", "symbol": "validate", "context_file": "server.py"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))

    # -- Worker that uses events handler (different context) --
    if n >= 4:
        files["worker.py"] = (
            '"""Background worker that uses the events handler."""\n\n'
            'from handlers.events.handler import Handler as EventHandler\n\n\n'
            'def process_events():\n'
            '    handler = EventHandler()\n'
            '    handler.handle({"type": "order_created", "order_id": "123"})\n'
        )
        questions.append(GroundTruthQuestion(
            id="nc_q5",
            question="In worker.py, EventHandler is an alias. What does it point to?",
            workflow_type="GOTO_DEFINITION_HINT",
            expected={"file": "handlers/events/handler.py", "symbol": "Handler", "alias": "EventHandler"},
            scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
            difficulty=Difficulty.HARD,
        ))

    # -- Filler for larger sizes --
    _extra = {SizeTier.XS: 0, SizeTier.S: 0, SizeTier.M: 5, SizeTier.L: 30, SizeTier.XL: 100}
    for i in range(_extra[size]):
        fname = f"middleware/mw_{i:03d}.py"
        if "middleware/__init__.py" not in files:
            files["middleware/__init__.py"] = ""
        src = (
            f'"""Middleware {i}."""\n\n\n'
            f'def apply_{i}(request):\n'
            f'    return request\n'
        )
        src = _pad_with_helpers(src, target_lines, f"mw{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"name_collision_{size.value}",
        challenge="name_collision",
        size_tier=size,
        files=files,
        questions=questions,
        description="Multiple files containing identically-named symbols to test disambiguation",
    )
