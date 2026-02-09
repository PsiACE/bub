"""Error definitions for Republic."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ErrorKind(StrEnum):
    """Stable error kinds for caller decisions."""

    INVALID_INPUT = "invalid_input"
    CONFIG = "config"
    PROVIDER = "provider"
    TOOL = "tool"
    TEMPORARY = "temporary"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepublicError(Exception):
    """Public error type for Republic."""

    kind: ErrorKind
    message: str
    cause: Exception | None = None

    def __str__(self) -> str:
        return f"[{self.kind.value}] {self.message}"

    def with_cause(self, cause: Exception) -> RepublicError:
        return replace(self, cause=cause)
