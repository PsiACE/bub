"""Append-only tape primitives owned by Bub."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time
from datetime import date as date_type
from typing import Any, NoReturn, Protocol, Self, overload

from typing_extensions import TypeIs

from bub.runtime import BubError, ErrorKind


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TapeEntry:
    """A single append-only entry in a tape."""

    id: int
    kind: str
    payload: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)
    date: str = field(default_factory=utc_now)

    def copy(self) -> TapeEntry:
        return TapeEntry(self.id, self.kind, dict(self.payload), dict(self.meta), self.date)


class TapeStore(Protocol):
    """Append-only tape storage interface."""

    def list_tapes(self) -> list[str]: ...

    def reset(self, tape: str) -> None: ...

    def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]: ...

    def append(self, tape: str, entry: TapeEntry) -> None: ...


class AsyncTapeStore(Protocol):
    """Async append-only tape storage interface."""

    async def list_tapes(self) -> list[str]: ...

    async def reset(self, tape: str) -> None: ...

    async def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]: ...

    async def append(self, tape: str, entry: TapeEntry) -> None: ...


def is_async_tape_store(store: TapeStore | AsyncTapeStore) -> TypeIs[AsyncTapeStore]:
    return hasattr(store, "append") and inspect.iscoroutinefunction(store.append)


@dataclass(frozen=True)
class TapeQuery[T: TapeStore | AsyncTapeStore]:
    tape: str
    store: T
    _query: str | None = None
    _between_dates: tuple[str, str] | None = None
    _kinds: tuple[str, ...] = field(default_factory=tuple)
    _limit: int | None = None

    def query(self, value: str) -> Self:
        return replace(self, _query=value)

    def between_dates(self, start: str | date_type, end: str | date_type) -> Self:
        start_value = start.isoformat() if isinstance(start, date_type) else start
        end_value = end.isoformat() if isinstance(end, date_type) else end
        return replace(self, _between_dates=(start_value, end_value))

    def kinds(self, *kinds: str) -> Self:
        return replace(self, _kinds=kinds)

    def limit(self, value: int) -> Self:
        return replace(self, _limit=value)

    @overload
    def all(self: TapeQuery[TapeStore]) -> Iterable[TapeEntry]: ...

    @overload
    async def all(self: TapeQuery[AsyncTapeStore]) -> Iterable[TapeEntry]: ...

    def all(self) -> Iterable[TapeEntry] | Coroutine[None, None, Iterable[TapeEntry]]:
        return self.store.fetch_all(self)


def _parse_datetime_boundary(value: str, *, is_end: bool) -> datetime:
    if "T" not in value and " " not in value:
        try:
            parsed_date = date_type.fromisoformat(value)
        except ValueError:
            pass
        else:
            boundary_time = time.max if is_end else time.min
            return datetime.combine(parsed_date, boundary_time, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed_date = date_type.fromisoformat(value)
        except ValueError as exc:
            raise BubError(ErrorKind.INVALID_INPUT, f"Invalid ISO date or datetime: '{value}'.") from exc
        boundary_time = time.max if is_end else time.min
        parsed = datetime.combine(parsed_date, boundary_time, tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _entry_in_datetime_range(entry: TapeEntry, start_dt: datetime, end_dt: datetime) -> bool:
    entry_dt = _parse_datetime_boundary(entry.date, is_end=False)
    return start_dt <= entry_dt <= end_dt


def _entry_matches_query(entry: TapeEntry, query: str) -> bool:
    needle = query.casefold()
    haystack = json.dumps(
        {
            "kind": entry.kind,
            "date": entry.date,
            "payload": entry.payload,
            "meta": entry.meta,
        },
        sort_keys=True,
        default=str,
    ).casefold()
    return needle in haystack


class InMemoryQueryMixin:
    """Mixin to implement in-memory query support for simple stores."""

    def read(self, tape: str) -> list[TapeEntry] | None:
        raise NotImplementedError("InMemoryQueryMixin requires a read() method to be implemented.")

    def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]:
        entries = self.read(query.tape) or []
        sliced = list(entries)
        if query._between_dates is not None:
            start_date, end_date = query._between_dates
            start_dt = _parse_datetime_boundary(start_date, is_end=False)
            end_dt = _parse_datetime_boundary(end_date, is_end=True)
            if start_dt > end_dt:
                raise BubError(ErrorKind.INVALID_INPUT, "Start date must be earlier than or equal to end date.")
            sliced = [entry for entry in sliced if _entry_in_datetime_range(entry, start_dt, end_dt)]
        if query._query:
            sliced = [entry for entry in sliced if _entry_matches_query(entry, query._query)]
        if query._kinds:
            sliced = [entry for entry in sliced if entry.kind in query._kinds]
        if query._limit is not None:
            sliced = sliced[: query._limit]
        return sliced


class InMemoryTapeStore(InMemoryQueryMixin):
    """In-memory tape storage."""

    def __init__(self) -> None:
        self._tapes: dict[str, list[TapeEntry]] = {}
        self._next_id: dict[str, int] = {}

    def list_tapes(self) -> list[str]:
        return sorted(self._tapes.keys())

    def reset(self, tape: str) -> None:
        self._tapes.pop(tape, None)
        self._next_id.pop(tape, None)

    def read(self, tape: str) -> list[TapeEntry] | None:
        entries = self._tapes.get(tape)
        if entries is None:
            return None
        return [entry.copy() for entry in entries]

    def append(self, tape: str, entry: TapeEntry) -> None:
        next_id = self._next_id.get(tape, 1)
        self._next_id[tape] = next_id + 1
        stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta), entry.date)
        self._tapes.setdefault(tape, []).append(stored)


class AsyncTapeStoreAdapter:
    """Adapt a sync TapeStore to AsyncTapeStore."""

    def __init__(self, store: TapeStore) -> None:
        self._store = store

    async def list_tapes(self) -> list[str]:
        return await asyncio.to_thread(self._store.list_tapes)

    async def reset(self, tape: str) -> None:
        await asyncio.to_thread(self._store.reset, tape)

    async def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]:
        return await asyncio.to_thread(self._store.fetch_all, query)

    async def append(self, tape: str, entry: TapeEntry) -> None:
        await asyncio.to_thread(self._store.append, tape, entry)


class UnavailableTapeStore:
    """Sync TapeStore sentinel that always fails with a clear message."""

    def __init__(self, message: str) -> None:
        self._message = message

    def _raise(self) -> NoReturn:
        raise BubError(ErrorKind.INVALID_INPUT, self._message)

    def list_tapes(self) -> list[str]:
        self._raise()

    def reset(self, tape: str) -> None:
        self._raise()

    def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]:
        self._raise()

    def append(self, tape: str, entry: TapeEntry) -> None:
        self._raise()
