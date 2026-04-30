"""Shared log event model and routing."""

from enum import Enum

from pydantic import BaseModel


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogEvent(BaseModel):
    level: LogLevel = LogLevel.INFO
    source: str = ""
    message: str = ""
    metadata: dict = {}
