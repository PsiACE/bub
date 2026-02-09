"""Tape stores for Republic."""

from __future__ import annotations

import builtins
from typing import Protocol

from republic.tape.entries import TapeEntry


class TapeStore(Protocol):
    """Append-only tape storage interface."""

    def list_tapes(self) -> builtins.list[str]: ...

    def reset(self, tape: str) -> None: ...

    def read(self, tape: str) -> builtins.list[TapeEntry] | None: ...

    def append(self, tape: str, entry: TapeEntry) -> None: ...


class InMemoryTapeStore:
    """In-memory tape storage (not thread-safe)."""

    def __init__(self) -> None:
        self._tapes: dict[str, list[TapeEntry]] = {}
        self._next_id: dict[str, int] = {}

    def list_tapes(self) -> builtins.list[str]:
        return sorted(self._tapes.keys())

    def reset(self, tape: str) -> None:
        self._tapes.pop(tape, None)
        self._next_id.pop(tape, None)

    def read(self, tape: str) -> builtins.list[TapeEntry] | None:
        entries = self._tapes.get(tape)
        if entries is None:
            return None
        return [entry.copy() for entry in entries]

    def append(self, tape: str, entry: TapeEntry) -> None:
        next_id = self._next_id.get(tape, 1)
        self._next_id[tape] = next_id + 1
        stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
        self._tapes.setdefault(tape, []).append(stored)
