from __future__ import annotations

import contextlib
import contextvars
import itertools
import json
import threading
from collections.abc import AsyncGenerator, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import cast

from loguru import logger
from republic import AsyncTapeStore, TapeEntry, TapeQuery
from republic.tape import AsyncTapeStoreAdapter, InMemoryQueryMixin, InMemoryTapeStore, TapeStore
from republic.tape.store import is_async_tape_store

current_store: contextvars.ContextVar[TapeStore] = contextvars.ContextVar("current_store")


class ForkTapeStore:
    def __init__(self, parent: AsyncTapeStore | TapeStore) -> None:
        if is_async_tape_store(parent):
            self._parent = parent
        else:
            self._parent = AsyncTapeStoreAdapter(parent)

    @property
    def _current(self) -> TapeStore:
        return current_store.get(_emtpy_store)

    async def list_tapes(self) -> list[str]:
        return cast(list[str], await self._parent.list_tapes())

    async def reset(self, tape: str) -> None:
        self._current.reset(tape)
        await self._parent.reset(tape)

    async def fetch_all(self, query: TapeQuery[AsyncTapeStore]) -> Iterable[TapeEntry]:
        try:
            parent_entries = await self._parent.fetch_all(query)
        except Exception:
            parent_entries = []
        this_entries: list[TapeEntry] = []
        if hasattr(self._current, "read"):
            for entry in cast(list[TapeEntry], self._current.read(query.tape) or []):
                if query._kinds and entry.kind not in query._kinds:
                    continue
                if entry.kind == "anchor":  # noqa: SIM102
                    if query._after_last or (query._after_anchor and entry.payload.get("name") == query._after_anchor):
                        this_entries.clear()
                        parent_entries = []
                this_entries.append(entry)
        return itertools.chain(parent_entries, this_entries)

    async def append(self, tape: str, entry: TapeEntry) -> None:
        self._current.append(tape, entry)

    @contextlib.asynccontextmanager
    async def fork(self, tape: str) -> AsyncGenerator[None, None]:
        store = InMemoryTapeStore()
        token = current_store.set(store)
        try:
            yield
        finally:
            current_store.reset(token)
            entries = store.read(tape)
            if entries:
                count = len(entries)
                for entry in entries:
                    await self._parent.append(tape, entry)
                logger.info(f'Merged {count} entries into tape "{tape}"')


class EmptyTapeStore:
    """Sync TapeStore sentinel that always returns empty results."""

    def list_tapes(self) -> list[str]:
        return []

    def reset(self, tape: str) -> None:
        pass

    def fetch_all(self, query: TapeQuery) -> Iterable[TapeEntry]:
        return []

    def append(self, tape: str, entry: TapeEntry) -> None:
        pass


_emtpy_store = EmptyTapeStore()


class FileTapeStore(InMemoryQueryMixin):
    """TapeStore implementation that persists tapes as JSONL files under a directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def _tape_file(self, tape: str) -> TapeFile:
        return TapeFile(self._directory / f"{tape}.jsonl")

    def list_tapes(self) -> list[str]:
        result: list[str] = []
        for file in self._directory.glob("*.jsonl"):
            filename = file.stem
            if filename.count("__") != 1:
                continue
            result.append(filename)
        return result

    def reset(self, tape: str) -> None:
        self._tape_file(tape).reset()

    def append(self, tape: str, entry: TapeEntry) -> None:
        self._tape_file(tape).append(entry)

    def read(self, tape: str) -> list[TapeEntry] | None:
        return self._tape_file(tape).read()


class TapeFile:
    """Helper for one tape file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._read_entries: list[TapeEntry] = []
        self._read_offset = 0

    def _next_id(self) -> int:
        if self._read_entries:
            return cast(int, self._read_entries[-1].id + 1)
        return 1

    def _reset(self) -> None:
        self._read_entries = []
        self._read_offset = 0

    def reset(self) -> None:
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            self._reset()

    def read(self) -> list[TapeEntry]:
        with self._lock:
            return self._read_locked()

    def _read_locked(self) -> list[TapeEntry]:
        if not self.path.exists():
            self._reset()
            return []

        file_size = self.path.stat().st_size
        if file_size < self._read_offset:
            # The file was truncated or replaced, so cached entries are stale.
            self._reset()

        with self.path.open("r", encoding="utf-8") as handle:
            handle.seek(self._read_offset)
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry = self.entry_from_payload(payload)
                if entry is not None:
                    self._read_entries.append(entry)
            self._read_offset = handle.tell()

        return list(self._read_entries)

    @staticmethod
    def entry_from_payload(payload: object) -> TapeEntry | None:
        if not isinstance(payload, dict):
            return None
        entry_id = payload.get("id")
        kind = payload.get("kind")
        entry_payload = payload.get("payload")
        meta = payload.get("meta")
        if not isinstance(entry_id, int):
            return None
        if not isinstance(kind, str):
            return None
        if not isinstance(entry_payload, dict):
            return None
        if not isinstance(meta, dict):
            meta = {}
        timestamp = payload.get("timestamp", 0.0)
        return TapeEntry(entry_id, kind, dict(entry_payload), dict(meta), timestamp)

    def append(self, entry: TapeEntry) -> None:
        with self._lock:
            # Keep cache and offset in sync before allocating new IDs.
            self._read_locked()
            with self.path.open("a", encoding="utf-8") as handle:
                next_id = self._next_id()
                stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
                handle.write(json.dumps(asdict(stored), ensure_ascii=False) + "\n")
                self._read_entries.append(stored)
                self._read_offset = handle.tell()
