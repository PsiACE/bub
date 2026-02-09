"""Structured results and errors for Republic."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from republic.core.errors import ErrorKind


@dataclass(frozen=True)
class ErrorPayload:
    kind: ErrorKind
    message: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class StructuredOutput:
    value: Any | None
    error: ErrorPayload | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class StreamState:
    error: ErrorPayload | None = None
    usage: dict[str, Any] | None = None


class TextStream:
    def __init__(self, iterator: Iterator[str], *, state: StreamState | None = None) -> None:
        self._iterator = iterator
        self._state = state or StreamState()

    def __iter__(self) -> Iterator[str]:
        return self._iterator

    @property
    def error(self) -> ErrorPayload | None:
        return self._state.error

    @property
    def usage(self) -> dict[str, Any] | None:
        return self._state.usage


class AsyncTextStream:
    def __init__(self, iterator: AsyncIterator[str], *, state: StreamState | None = None) -> None:
        self._iterator = iterator
        self._state = state or StreamState()

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterator

    @property
    def error(self) -> ErrorPayload | None:
        return self._state.error

    @property
    def usage(self) -> dict[str, Any] | None:
        return self._state.usage


@dataclass(frozen=True)
class StreamEvent:
    kind: Literal[
        "text",
        "tool_call",
        "tool_result",
        "usage",
        "error",
        "final",
    ]
    data: dict[str, Any]


class StreamEvents:
    def __init__(self, iterator: Iterator[StreamEvent], *, state: StreamState | None = None) -> None:
        self._iterator = iterator
        self._state = state or StreamState()

    def __iter__(self) -> Iterator[StreamEvent]:
        return self._iterator

    @property
    def error(self) -> ErrorPayload | None:
        return self._state.error

    @property
    def usage(self) -> dict[str, Any] | None:
        return self._state.usage


class AsyncStreamEvents:
    def __init__(self, iterator: AsyncIterator[StreamEvent], *, state: StreamState | None = None) -> None:
        self._iterator = iterator
        self._state = state or StreamState()

    def __aiter__(self) -> AsyncIterator[StreamEvent]:
        return self._iterator

    @property
    def error(self) -> ErrorPayload | None:
        return self._state.error

    @property
    def usage(self) -> dict[str, Any] | None:
        return self._state.usage


@dataclass(frozen=True)
class ToolExecution:
    tool_calls: list[dict[str, Any]]
    tool_results: list[Any]
    error: ErrorPayload | None = None


@dataclass(frozen=True)
class ToolAutoResult:
    kind: Literal["text", "tools", "error"]
    text: str | None
    tool_calls: list[dict[str, Any]]
    tool_results: list[Any]
    error: ErrorPayload | None

    @classmethod
    def text_result(cls, text: str) -> ToolAutoResult:
        return cls(
            kind="text",
            text=text,
            tool_calls=[],
            tool_results=[],
            error=None,
        )

    @classmethod
    def tools_result(
        cls,
        tool_calls: list[dict[str, Any]],
        tool_results: list[Any],
    ) -> ToolAutoResult:
        return cls(
            kind="tools",
            text=None,
            tool_calls=tool_calls,
            tool_results=tool_results,
            error=None,
        )

    @classmethod
    def error_result(
        cls,
        error: ErrorPayload,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_results: list[Any] | None = None,
    ) -> ToolAutoResult:
        return cls(
            kind="error",
            text=None,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            error=error,
        )
