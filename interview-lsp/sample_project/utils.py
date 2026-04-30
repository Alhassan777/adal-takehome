import json
from pathlib import Path
from datetime import datetime


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure_directory(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def truncate(text: str, length: int = 100) -> str:
    if len(text) <= length:
        return text
    return text[:length] + "..."
