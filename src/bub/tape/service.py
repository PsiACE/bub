"""High-level tape service."""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Generator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from loguru import logger
from rapidfuzz import fuzz, process
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
    entries_since_last_anchor: int


_tape_context: ContextVar[Tape] = ContextVar("tape")
WORD_PATTERN = re.compile(r"[a-z0-9_/-]+")
MIN_FUZZY_QUERY_LENGTH = 3
MIN_FUZZY_SCORE = 80
MAX_FUZZY_CANDIDATES = 128


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
        self._bootstrapped = False

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
            logger.info("Merged forked tape '{}' back into '{}'", fork_name, self._tape.name)

    async def ensure_bootstrap_anchor(self) -> None:
        if self._bootstrapped:
            return
        self._bootstrapped = True
        anchors = list(await self._tape.query_async.kinds("anchor").all())
        if anchors:
            return
        await self.handoff("session/start", state={"owner": "human"})

    async def handoff(self, name: str, *, state: dict[str, Any] | None = None) -> list[TapeEntry]:
        return cast(list[TapeEntry], await self.tape.handoff_async(name, state=state))

    async def append_event(self, name: str, data: dict[str, Any]) -> None:
        await self.tape.append_async(TapeEntry.event(name, data=data))

    async def append_system(self, content: str) -> None:
        await self.tape.append_async(TapeEntry.system(content))

    async def info(self) -> TapeInfo:
        entries = list(await self._tape.query_async.all())
        anchors = [entry for entry in entries if entry.kind == "anchor"]
        last_anchor = anchors[-1].payload.get("name") if anchors else None
        if last_anchor is not None:
            entries_since_last_anchor = sum(1 for entry in entries if entry.id > anchors[-1].id)
        else:
            entries_since_last_anchor = len(entries)
        return TapeInfo(
            name=self._tape.name,
            entries=len(entries),
            anchors=len(anchors),
            last_anchor=str(last_anchor) if last_anchor else None,
            entries_since_last_anchor=entries_since_last_anchor,
        )

    async def reset(self, *, archive: bool = False) -> str:
        archive_path: Path | None = None
        if archive and self._store is not None:
            archive_path = self._store.archive(self._tape.name)
        await self._tape.reset_async()
        state = {"owner": "human"}
        if archive_path is not None:
            state["archived"] = str(archive_path)
        await self._tape.handoff_async("session/start", state=state)
        return f"Archived: {archive_path}" if archive_path else "ok"

    async def anchors(self, *, limit: int = 20) -> list[AnchorSummary]:
        entries = list(await self._tape.query_async.kinds("anchor").all())
        results: list[AnchorSummary] = []
        for entry in entries[-limit:]:
            name = str(entry.payload.get("name", "-"))
            state = entry.payload.get("state")
            state_dict: dict[str, object] = dict(state) if isinstance(state, dict) else {}
            results.append(AnchorSummary(name=name, state=state_dict))
        return results

    async def between_anchors(self, start: str, end: str, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query_async.between_anchors(start, end)
        if kinds:
            query = query.kinds(*kinds)
        return list(await query.all())

    async def after_anchor(self, anchor: str, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query_async.after_anchor(anchor)
        if kinds:
            query = query.kinds(*kinds)
        return list(await query.all())

    async def from_last_anchor(self, *, kinds: tuple[str, ...] = ()) -> list[TapeEntry]:
        query = self.tape.query_async.last_anchor()
        if kinds:
            query = query.kinds(*kinds)
        return list(await query.all())

    async def search(self, query: str, *, limit: int = 20, all_tapes: bool = False) -> list[TapeEntry]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        results: list[TapeEntry] = []
        tapes = [self.tape]
        if all_tapes:
            tapes = [self._llm.tape(name) for name in self._store.list_tapes()]

        for tape in tapes:
            count = 0
            for entry in reversed(list(await tape.query_async.kinds("message").all())):
                payload_text = json.dumps(entry.payload, ensure_ascii=False)
                entry_meta = getattr(entry, "meta", {})
                meta_text = json.dumps(entry_meta, ensure_ascii=False)

                if (
                    normalized_query in payload_text.lower() or normalized_query in meta_text.lower()
                ) or self._is_fuzzy_match(normalized_query, payload_text, meta_text):
                    results.append(entry)
                    count += 1
                    if count >= limit:
                        break
        return results

    @staticmethod
    def _is_fuzzy_match(normalized_query: str, payload_text: str, meta_text: str) -> bool:
        if len(normalized_query) < MIN_FUZZY_QUERY_LENGTH:
            return False

        query_tokens = WORD_PATTERN.findall(normalized_query)
        if not query_tokens:
            return False
        query_phrase = " ".join(query_tokens)
        window_size = len(query_tokens)

        source_tokens = WORD_PATTERN.findall(payload_text.lower()) + WORD_PATTERN.findall(meta_text.lower())
        if not source_tokens:
            return False

        candidates: list[str] = []
        for token in source_tokens:
            candidates.append(token)
            if len(candidates) >= MAX_FUZZY_CANDIDATES:
                break

        if window_size > 1:
            max_window_start = len(source_tokens) - window_size + 1
            for idx in range(max(0, max_window_start)):
                candidates.append(" ".join(source_tokens[idx : idx + window_size]))
                if len(candidates) >= MAX_FUZZY_CANDIDATES:
                    break

        best_match = process.extractOne(
            query_phrase,
            candidates,
            scorer=fuzz.WRatio,
            score_cutoff=MIN_FUZZY_SCORE,
        )
        return best_match is not None
