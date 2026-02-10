"""High-level tape service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from republic import LLM, TapeEntry
from republic.tape import Tape

from bub.tape.anchors import AnchorSummary
from bub.tape.memory import MemoryZone
from bub.tape.store import FileTapeStore


@dataclass(frozen=True)
class TapeInfo:
    """Runtime tape info summary."""

    name: str
    entries: int
    anchors: int
    last_anchor: str | None


class TapeService:
    """Tape helper with app-specific operations."""

    def __init__(self, llm: LLM, tape_name: str, *, store: FileTapeStore | None = None) -> None:
        self._tape: Tape = llm.tape(tape_name)
        self._store = store
        self._memory: MemoryZone | None = None

    @property
    def memory(self) -> MemoryZone:
        """Access the memory zone for this tape."""
        if self._memory is None:
            self._memory = MemoryZone(self)
        return self._memory

    @property
    def tape_name(self) -> str:
        return cast(str, self._tape.name)

    @property
    def tape(self) -> Tape:
        return self._tape

    def ensure_bootstrap_anchor(self) -> None:
        anchors = [entry for entry in self.read_entries() if entry.kind == "anchor"]
        if anchors:
            return
        self.handoff("session/start", state={"owner": "human"})

    def read_entries(self) -> list[TapeEntry]:
        return cast(list[TapeEntry], self._tape.read_entries())

    def handoff(self, name: str, *, state: dict[str, Any] | None = None) -> list[TapeEntry]:
        return cast(list[TapeEntry], self._tape.handoff(name, state=state))

    def append_anchor(self, name: str, *, state: dict[str, Any] | None = None) -> None:
        """Write a bare anchor entry (no companion handoff event)."""
        self._tape.append(TapeEntry.anchor(name, state=state))

    def append_event(self, name: str, data: dict[str, Any]) -> None:
        self._tape.append(TapeEntry.event(name, data=data))

    def append_system(self, content: str) -> None:
        self._tape.append(TapeEntry.system(content))

    def info(self) -> TapeInfo:
        entries = self.read_entries()
        anchors = [entry for entry in entries if entry.kind == "anchor"]
        last_anchor = anchors[-1].payload.get("name") if anchors else None
        return TapeInfo(
            name=self._tape.name,
            entries=len(entries),
            anchors=len(anchors),
            last_anchor=str(last_anchor) if last_anchor else None,
        )

    def reset(self, *, archive: bool = False) -> str:
        if archive and self._store is not None:
            archive_path = self._store.archive(self._tape.name)
            self._tape.reset()
            self._memory = None
            self.ensure_bootstrap_anchor()
            self.memory.ensure()
            if archive_path is not None:
                return f"archived: {archive_path}"
        self._tape.reset()
        self._memory = None
        self.ensure_bootstrap_anchor()
        self.memory.ensure()
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
        query = self._tape.query().between_anchors(start, end)
        if kinds:
            query = query.kinds(*kinds)
        result = query.all()
        return result.entries if result.error is None else []

    def after_anchor(self, anchor: str, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self._tape.query().after_anchor(anchor)
        if kinds:
            query = query.kinds(*kinds)
        result = query.all()
        return result.entries if result.error is None else []

    def from_last_anchor(self, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self._tape.query().last_anchor()
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
