"""Query helpers for tape entries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from republic.core.errors import ErrorKind
from republic.core.results import ErrorPayload
from republic.tape.entries import TapeEntry
from republic.tape.store import TapeStore


@dataclass(frozen=True)
class QueryResult:
    entries: list[TapeEntry]
    error: ErrorPayload | None = None


@dataclass(frozen=True)
class TapeQuery:
    tape: str
    store: TapeStore
    _after_anchor: str | None = None
    _after_last: bool = False
    _between: tuple[str, str] | None = None
    _kinds: tuple[str, ...] = field(default_factory=tuple)
    _limit: int | None = None

    def after_anchor(self, name: str) -> TapeQuery:
        if not name:
            return TapeQuery(
                tape=self.tape,
                store=self.store,
                _after_anchor="",
                _after_last=False,
                _between=self._between,
                _kinds=self._kinds,
                _limit=self._limit,
            )
        return TapeQuery(
            tape=self.tape,
            store=self.store,
            _after_anchor=name,
            _after_last=False,
            _between=self._between,
            _kinds=self._kinds,
            _limit=self._limit,
        )

    def last_anchor(self) -> TapeQuery:
        return TapeQuery(
            tape=self.tape,
            store=self.store,
            _after_anchor=None,
            _after_last=True,
            _between=self._between,
            _kinds=self._kinds,
            _limit=self._limit,
        )

    def between_anchors(self, start: str, end: str) -> TapeQuery:
        return TapeQuery(
            tape=self.tape,
            store=self.store,
            _after_anchor=self._after_anchor,
            _after_last=self._after_last,
            _between=(start, end),
            _kinds=self._kinds,
            _limit=self._limit,
        )

    def kinds(self, *kinds: str) -> TapeQuery:
        return TapeQuery(
            tape=self.tape,
            store=self.store,
            _after_anchor=self._after_anchor,
            _after_last=self._after_last,
            _between=self._between,
            _kinds=tuple(kinds),
            _limit=self._limit,
        )

    def limit(self, value: int) -> TapeQuery:
        return TapeQuery(
            tape=self.tape,
            store=self.store,
            _after_anchor=self._after_anchor,
            _after_last=self._after_last,
            _between=self._between,
            _kinds=self._kinds,
            _limit=value,
        )

    def all(self) -> QueryResult:
        entries, error = self._read_entries()
        if self._limit is not None:
            return QueryResult(entries[: self._limit], error)
        return QueryResult(entries, error)

    def _read_entries(self) -> tuple[list[TapeEntry], ErrorPayload | None]:
        entries = self.store.read(self.tape) or []
        start_index = 0
        end_index: int | None = None
        error: ErrorPayload | None = None

        if self._between is not None:
            start_name, end_name = self._between
            start_idx = _anchor_index(entries, start_name, default=-1, forward=False)
            if start_idx < 0:
                return [], ErrorPayload(ErrorKind.NOT_FOUND, f"Anchor '{start_name}' was not found.")
            end_idx = _anchor_index(entries, end_name, default=-1, forward=True, start=start_idx + 1)
            if end_idx < 0:
                return [], ErrorPayload(ErrorKind.NOT_FOUND, f"Anchor '{end_name}' was not found.")
            start_index = min(start_idx + 1, len(entries))
            end_index = min(max(start_index, end_idx), len(entries))
        elif self._after_last:
            anchor_index = _anchor_index(entries, None, default=-1, forward=False)
            if anchor_index < 0:
                return [], ErrorPayload(ErrorKind.NOT_FOUND, "No anchors found in tape.")
            start_index = min(anchor_index + 1, len(entries))
        elif self._after_anchor is not None:
            anchor_index = _anchor_index(entries, self._after_anchor, default=-1, forward=False)
            if anchor_index < 0:
                return [], ErrorPayload(ErrorKind.NOT_FOUND, f"Anchor '{self._after_anchor}' was not found.")
            start_index = min(anchor_index + 1, len(entries))

        sliced = entries[start_index:end_index]
        if self._kinds:
            sliced = [entry for entry in sliced if entry.kind in self._kinds]
        return sliced, error


def _anchor_index(
    entries: Sequence[TapeEntry],
    name: str | None,
    *,
    default: int,
    forward: bool,
    start: int = 0,
) -> int:
    rng = range(start, len(entries)) if forward else range(len(entries) - 1, start - 1, -1)
    for idx in rng:
        entry = entries[idx]
        if entry.kind != "anchor":
            continue
        if name is not None and entry.payload.get("name") != name:
            continue
        return idx
    return default
