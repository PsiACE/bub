"""High-level tape service."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Generator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast

from republic import LLM, TapeEntry
from republic.tape import Tape

from bub.tape.anchors import AnchorSummary
from bub.tape.store import FileTapeStore


@dataclass(frozen=True)
class TapeInfo:
    """Runtime tape info summary."""

    name: str
    entries: int
    anchors: int
    last_anchor: str | None


_tape_context: ContextVar[Tape] = ContextVar("tape")


def current_tape() -> str:
    """Get the name of the current tape in context."""
    tape = _tape_context.get(None)
    if tape is None:
        return "-"
    return tape.name  # type: ignore[no-any-return]


class TapeService:
    """Tape helper with app-specific operations."""

    def __init__(self, llm: LLM, tape_name: str, *, store: FileTapeStore) -> None:
        self._llm = llm
        self._store = store
        self._tape = llm.tape(tape_name)

    @property
    def tape(self) -> Tape:
        return _tape_context.get(self._tape)

    @contextlib.contextmanager
    def fork_tape(self) -> Generator[Tape, None, None]:
        fork_name = self._store.fork(self._tape.name)
        reset_token = _tape_context.set(self._llm.tape(fork_name))
        try:
            yield _tape_context.get()
        finally:
            self._store.merge(fork_name, self._tape.name)
            _tape_context.reset(reset_token)

    def ensure_bootstrap_anchor(self) -> None:
        anchors = [entry for entry in self.read_entries() if entry.kind == "anchor"]
        if anchors:
            return
        self.handoff("session/start", state={"owner": "human"})

    def read_entries(self) -> list[TapeEntry]:
        return cast(list[TapeEntry], self.tape.read_entries())

    def handoff(self, name: str, *, state: dict[str, Any] | None = None) -> list[TapeEntry]:
        return cast(list[TapeEntry], self.tape.handoff(name, state=state))

    def append_event(self, name: str, data: dict[str, Any]) -> None:
        self.tape.append(TapeEntry.event(name, data=data))

    def append_system(self, content: str) -> None:
        self.tape.append(TapeEntry.system(content))

    def info(self) -> TapeInfo:
        entries = self.read_entries()
        anchors = [entry for entry in entries if entry.kind == "anchor"]
        last_anchor = anchors[-1].payload.get("name") if anchors else None
        return TapeInfo(
            name=self.tape.name,
            entries=len(entries),
            anchors=len(anchors),
            last_anchor=str(last_anchor) if last_anchor else None,
        )

    def reset(self, *, archive: bool = False) -> str:
        if archive and self._store is not None:
            archive_path = self._store.archive(self.tape.name)
            self.tape.reset()
            self.ensure_bootstrap_anchor()
            if archive_path is not None:
                return f"archived: {archive_path}"
        self.tape.reset()
        self.ensure_bootstrap_anchor()
        return "ok"

    def anchors(self, *, limit: int = 20) -> list[AnchorSummary]:
        entries = [entry for entry in self.read_entries() if entry.kind == "anchor"]
        results: list[AnchorSummary] = []
        for entry in entries[-limit:]:
            name = str(entry.payload.get("name", "-"))
            state = entry.payload.get("state")
            state_dict: dict[str, object] = dict(state) if isinstance(state, dict) else {}
            results.append(AnchorSummary(name=name, state=state_dict))
        return results

    def between_anchors(self, start: str, end: str, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query().between_anchors(start, end)
        if kinds:
            query = query.kinds(*kinds)
        result = query.all()
        return result.entries if result.error is None else []

    def after_anchor(self, anchor: str, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query().after_anchor(anchor)
        if kinds:
            query = query.kinds(*kinds)
        result = query.all()
        return result.entries if result.error is None else []

    def from_last_anchor(self, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query().last_anchor()
        if kinds:
            query = query.kinds(*kinds)
        result = query.all()
        return result.entries if result.error is None else []

    def search(self, query: str, *, limit: int = 20) -> list[TapeEntry]:
        if not query:
            return []
        results: list[TapeEntry] = []
        lowered = query.lower()
        for entry in self.read_entries():
            payload_text = json.dumps(entry.payload, ensure_ascii=False)
            meta_text = json.dumps(entry.meta, ensure_ascii=False)
            if lowered in payload_text.lower() or lowered in meta_text.lower() or lowered in entry.kind.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results
