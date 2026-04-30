"""Repository scanner: walk the file tree and collect metadata."""

from pathlib import Path

from ..config import DEFAULT_IGNORE_DIRS, SUPPORTED_EXTENSIONS
from ..models import FileRecord


def _should_ignore(path: Path, ignore_dirs: set[str]) -> bool:
    for part in path.parts:
        if part in ignore_dirs:
            return True
        for pattern in ignore_dirs:
            if "*" in pattern and path.match(pattern):
                return True
    return False


def scan_repo(
    root_path: str,
    ignore_dirs: set[str] | None = None,
) -> list[FileRecord]:
    """Walk the repository tree and collect file metadata for supported files."""
    if ignore_dirs is None:
        ignore_dirs = DEFAULT_IGNORE_DIRS

    root = Path(root_path).resolve()
    records: list[FileRecord] = []

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue

        rel = filepath.relative_to(root)

        if _should_ignore(rel, ignore_dirs):
            continue

        if filepath.suffix not in SUPPORTED_EXTENSIONS:
            continue

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            size_bytes = filepath.stat().st_size
        except (OSError, UnicodeDecodeError):
            continue

        records.append(
            FileRecord(
                path=str(rel),
                language="python" if filepath.suffix == ".py" else "python-stub",
                size_bytes=size_bytes,
                line_count=line_count,
            )
        )

    return records
