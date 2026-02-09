"""Tape entries for Republic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from republic.core.results import ErrorPayload


@dataclass(frozen=True)
class TapeEntry:
    """A single append-only entry in a tape."""

    id: int
    kind: str
    payload: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)

    def copy(self) -> TapeEntry:
        return TapeEntry(self.id, self.kind, dict(self.payload), dict(self.meta))

    @classmethod
    def message(cls, message: dict[str, Any], **meta: Any) -> TapeEntry:
        return cls(id=0, kind="message", payload=dict(message), meta=dict(meta))

    @classmethod
    def system(cls, content: str, **meta: Any) -> TapeEntry:
        return cls(id=0, kind="system", payload={"content": content}, meta=dict(meta))

    @classmethod
    def anchor(cls, name: str, state: dict[str, Any] | None = None, **meta: Any) -> TapeEntry:
        payload: dict[str, Any] = {"name": name}
        if state is not None:
            payload["state"] = dict(state)
        return cls(id=0, kind="anchor", payload=payload, meta=dict(meta))

    @classmethod
    def tool_call(cls, calls: list[dict[str, Any]], **meta: Any) -> TapeEntry:
        return cls(id=0, kind="tool_call", payload={"calls": calls}, meta=dict(meta))

    @classmethod
    def tool_result(cls, results: list[Any], **meta: Any) -> TapeEntry:
        return cls(id=0, kind="tool_result", payload={"results": results}, meta=dict(meta))

    @classmethod
    def error(cls, error: ErrorPayload, **meta: Any) -> TapeEntry:
        return cls(id=0, kind="error", payload=error.as_dict(), meta=dict(meta))

    @classmethod
    def event(cls, name: str, data: dict[str, Any] | None = None, **meta: Any) -> TapeEntry:
        payload: dict[str, Any] = {"name": name}
        if data is not None:
            payload["data"] = dict(data)
        return cls(id=0, kind="event", payload=payload, meta=dict(meta))
