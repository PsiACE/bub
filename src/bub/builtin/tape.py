import contextlib
import hashlib
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import json
from pydantic.dataclasses import dataclass
from rapidfuzz import fuzz, process
from republic import LLM, Tape, TapeEntry

WORD_PATTERN = re.compile(r"[a-z0-9_/-]+")
MIN_FUZZY_QUERY_LENGTH = 3
MIN_FUZZY_SCORE = 80
MAX_FUZZY_CANDIDATES = 128


@dataclass(frozen=True)
class TapeInfo:
    """Runtime tape info summary."""

    name: str
    entries: int
    anchors: int
    last_anchor: str | None
    entries_since_last_anchor: int
    last_token_usage: int | None


@dataclass(frozen=True)
class AnchorSummary:
    """Rendered anchor summary."""

    name: str
    state: dict[str, object]


class TapeService:
    def __init__(self, llm: LLM, archive_path: Path) -> None:
        self._llm = llm
        self._archive_path = archive_path

    async def info(self, tape_name: str) -> TapeInfo:
        tape = self._llm.tape(tape_name)
        entries = list(await tape.query_async.all())
        anchors = [entry for entry in entries if entry.kind == "anchor"]
        last_anchor = anchors[-1].payload.get("name") if anchors else None
        if last_anchor is not None:
            entries_since_last_anchor = [entry for entry in entries if entry.id > anchors[-1].id]
        else:
            entries_since_last_anchor = entries
        last_token_usage: int | None = None
        for entry in reversed(entries_since_last_anchor):
            if entry.kind == "event" and entry.payload.get("name") == "run":
                with contextlib.suppress(AttributeError):
                    token_usage = entry.payload.get("data", {}).get("usage", {}).get("total_tokens")
                    if token_usage and isinstance(token_usage, int):
                        last_token_usage = token_usage
                        break
        return TapeInfo(
            name=tape.name,
            entries=len(entries),
            anchors=len(anchors),
            last_anchor=str(last_anchor) if last_anchor else None,
            entries_since_last_anchor=len(entries_since_last_anchor),
            last_token_usage=last_token_usage,
        )

    async def ensure_bootstrap_anchor(self, tape_name: str) -> None:
        tape = self._llm.tape(tape_name)
        anchors = list(await tape.query_async.kinds("anchor").all())
        if not anchors:
            await tape.handoff_async("session/start", state={"owner": "human"})

    async def anchors(self, tape_name: str, limit: int = 20) -> list[AnchorSummary]:
        tape = self._llm.tape(tape_name)
        entries = list(await tape.query_async.kinds("anchor").all())
        results: list[AnchorSummary] = []
        for entry in entries[-limit:]:
            name = str(entry.payload.get("name", "-"))
            state = entry.payload.get("state")
            state_dict: dict[str, object] = dict(state) if isinstance(state, dict) else {}
            results.append(AnchorSummary(name=name, state=state_dict))
        return results

    async def _archive(self, tape_name: str) -> Path:
        tape = self._llm.tape(tape_name)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self._archive_path.mkdir(parents=True, exist_ok=True)
        archive_path = self._archive_path / f"{tape.name}.jsonl.{stamp}.bak"
        with archive_path.open("w", encoding="utf-8") as f:
            for entry in await tape.query_async.all():
                f.write(json.dumps(asdict(entry)) + "\n")
        return archive_path

    async def reset(self, tape_name: str, *, archive: bool = False) -> str:
        tape = self._llm.tape(tape_name)
        archive_path: Path | None = None
        if archive:
            archive_path = await self._archive(tape_name)
        await tape.reset_async()
        state = {"owner": "human"}
        if archive_path is not None:
            state["archived"] = str(archive_path)
        await tape.handoff_async("session/start", state=state)
        return f"Archived: {archive_path}" if archive_path else "ok"

    async def handoff(self, tape_name: str, *, name: str, state: dict[str, Any] | None = None) -> list[TapeEntry]:
        tape = self._llm.tape(tape_name)
        entries = await tape.handoff_async(name, state=state)
        return cast(list[TapeEntry], entries)

    async def search(self, tape_name: str, query: str, *, limit: int = 20) -> list[TapeEntry]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        results: list[TapeEntry] = []
        tapes = [self._llm.tape(tape_name)]

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

    async def append_event(self, tape_name: str, name: str, payload: dict[str, Any], **meta: Any) -> None:
        tape = self._llm.tape(tape_name)
        await tape.append_async(TapeEntry.event(name=name, payload=payload, **meta))

    def session_tape(self, session_id: str) -> Tape:
        tape_name = hashlib.md5(session_id.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        return self._llm.tape(tape_name)
