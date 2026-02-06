"""Tape service helpers for Bub."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from republic.tape.entries import TapeEntry
from republic.tape.query import TapeQuery
from republic.tape.store import TapeStore

LANE_MAIN = "main"
LANE_WORK = "work"
LANE_CONTROL = "control"
META_LANE = "lane"
META_VIEW = "view"
META_CONTEXT = "context"
ENTRY_PREVIEW_MAX_LEN = 120
ENTRY_PREVIEW_TRUNCATE_LEN = 117
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class CommandRecord:
    name: str
    intent: str
    status: str
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    elapsed_ms: int | None
    origin: str


class TapeService:
    """High-level operations on a tape store."""

    def __init__(
        self,
        store: TapeStore,
        tape: str,
    ) -> None:
        self._store = store
        self._tape = tape

    @property
    def tape(self) -> str:
        return self._tape

    def entries(self) -> list[TapeEntry]:
        return self._store.read(self._tape) or []

    def context_messages(self) -> list[dict[str, str]]:
        entries = self.entries()
        messages: list[dict[str, str]] = []
        for entry in entries:
            if entry.kind != "message":
                continue
            if entry.meta.get(META_CONTEXT, True) is False:
                continue
            payload = entry.payload
            if not isinstance(payload, dict):
                continue
            role = payload.get("role")
            content = payload.get("content")
            if isinstance(role, str):
                messages.append({"role": role, "content": str(content or "")})
        return messages

    def record_user_message(self, content: str) -> None:
        self._append_message(
            {"role": "user", "content": content},
            meta={META_LANE: LANE_MAIN, META_VIEW: True, META_CONTEXT: False},
        )

    def record_assistant_message(self, content: str) -> None:
        if not content.strip():
            return
        self._append_message(
            {"role": "assistant", "content": content},
            meta={META_LANE: LANE_MAIN, META_VIEW: True, META_CONTEXT: True},
        )

    def record_context_message(self, content: str) -> None:
        if not content.strip():
            return
        self._append_message(
            {"role": "user", "content": content},
            meta={META_LANE: LANE_CONTROL, META_VIEW: False, META_CONTEXT: True},
        )

    def record_tool_event(self, kind: str, payload: dict) -> None:
        meta_payload = {
            META_LANE: LANE_WORK,
            META_VIEW: False,
            META_CONTEXT: False,
            "ts": int(time.time()),
        }
        entry = TapeEntry(0, kind, payload, meta_payload)
        self._store.append(self._tape, entry)

    def record_loop(self, loop_id: str, status: str, *, detail: str | None = None) -> None:
        payload = {"id": loop_id, "status": status}
        if detail:
            payload["detail"] = detail
        meta_payload = {
            META_LANE: LANE_CONTROL,
            META_VIEW: False,
            META_CONTEXT: False,
            "ts": int(time.time()),
        }
        entry = TapeEntry(0, "loop", payload, meta_payload)
        self._store.append(self._tape, entry)

    def search(
        self,
        query: str,
        *,
        after: str | None = None,
        kinds: Iterable[str] | None = None,
        limit: int | None = None,
        case_sensitive: bool = False,
    ) -> str:
        if not query:
            return "error: query is required"
        entries = self._query_entries(after=after, kinds=kinds)
        matches = []
        haystack_query = query if case_sensitive else query.lower()
        for entry in entries:
            text = _entry_text(entry)
            if not text:
                continue
            haystack = text if case_sensitive else text.lower()
            if haystack_query in haystack:
                matches.append(_format_entry(entry, text))
                if limit is not None and len(matches) >= limit:
                    break
        if not matches:
            return "(no matches)"
        return "\n".join(matches)

    def anchors(self, *, limit: int | None = None) -> str:
        anchors = self._anchor_entries(limit=limit)
        if not anchors:
            return "(no anchors)"
        lines = []
        for entry in anchors:
            name = _anchor_name(entry)
            summary = _anchor_summary(entry)
            lines.append(f"{entry.id:4} anchor {name} summary={summary}")
        return "\n".join(lines)

    def info(self) -> str:
        entries = self.entries()
        count = len(entries)
        last_anchor = next((e for e in reversed(entries) if e.kind == "anchor"), None)
        anchor_name = last_anchor.payload.get("name") if last_anchor else "-"
        return f"tape={self._tape} entries={count} last_anchor={anchor_name}"

    def reset(self, *, archive: bool = False) -> str:
        archive_path = None
        if archive and hasattr(self._store, "archive"):
            archive_path = self._store.archive()
        self._store.reset(self._tape)
        if archive_path is not None:
            return f"archived: {archive_path}"
        return "ok"

    def handoff(
        self,
        name: str | None,
        *,
        summary: str | None = None,
        next_steps: str | None = None,
    ) -> TapeEntry:
        anchor_name = name or f"handoff/{time.strftime('%Y%m%d-%H%M%S')}"
        state = {
            "summary": summary,
            "next_steps": next_steps,
        }
        state = {key: value for key, value in state.items() if value}
        meta: dict[str, object] = {}
        meta.setdefault("ts", int(time.time()))
        meta.setdefault(META_LANE, LANE_MAIN)
        meta.setdefault(META_VIEW, True)
        meta.setdefault(META_CONTEXT, True)
        entry = TapeEntry.anchor(anchor_name, state=state or None, **meta)
        self._store.append(self._tape, entry)
        return entry

    def record_command(self, record: CommandRecord, *, meta: dict | None = None) -> None:
        payload = {
            "name": record.name,
            "intent": record.intent,
            "status": record.status,
            "stdout": record.stdout,
            "stderr": record.stderr,
            "exit_code": record.exit_code,
            "elapsed_ms": record.elapsed_ms,
            "origin": record.origin,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        meta_payload = dict(meta) if meta else {}
        meta_payload.setdefault("ts", int(time.time()))
        meta_payload.setdefault("by", "human" if record.origin == "human" else "assistant")
        meta_payload.setdefault("source", record.origin)
        lane = LANE_MAIN if record.origin == "human" else LANE_WORK
        meta_payload.setdefault(META_LANE, lane)
        meta_payload.setdefault(META_VIEW, lane == LANE_MAIN)
        meta_payload.setdefault(META_CONTEXT, False)
        entry = TapeEntry(0, "command", payload, meta_payload)
        self._store.append(self._tape, entry)

    def status_panel(self, *, debug: bool = False) -> str:
        loops = self._loop_states()
        anchors = self._anchor_entries(limit=5)
        commands = self._recent_commands(limit=5) if debug else []

        lines: list[str] = []
        lines.append("Bub Status")
        lines.append("" + "-" * 9)
        lines.append(f"Active Loops: {len([loop for loop in loops if loop['active']])}")
        for loop in loops:
            if loop["active"]:
                lines.append(f"- loop#{loop['id']} (last: {loop['age']})")

        lines.append("")
        lines.append("Recent Anchors")
        if not anchors:
            lines.append("- (none)")
        else:
            for entry in anchors:
                name = _anchor_name(entry)
                summary = _anchor_summary(entry)
                lines.append(f"- {name}  summary={summary}")

        if debug:
            lines.append("")
            lines.append("Recent Commands (debug)")
            if not commands:
                lines.append("- (none)")
            else:
                for cmd in commands:
                    lines.append(cmd)

        return "\n".join(lines)

    def _loop_states(self) -> list[dict[str, str | bool]]:
        entries = [entry for entry in self.entries() if entry.kind == "loop"]
        latest: dict[str, TapeEntry] = {}
        for entry in entries:
            loop_id = entry.payload.get("id") if isinstance(entry.payload, dict) else None
            if not isinstance(loop_id, str):
                continue
            latest[loop_id] = entry
        results: list[dict[str, str | bool]] = []
        for loop_id, entry in latest.items():
            status = entry.payload.get("status") if isinstance(entry.payload, dict) else None
            active = status == "start"
            ts = entry.meta.get("ts") if isinstance(entry.meta, dict) else None
            age = _format_age(ts)
            results.append({"id": loop_id, "active": active, "age": age})
        results.sort(key=lambda item: item["id"])
        return results

    def _anchor_entries(self, *, limit: int | None = None) -> list[TapeEntry]:
        anchors = self._query_entries(kinds=["anchor"])
        if limit is not None:
            anchors = anchors[:limit]
        return anchors

    def _recent_commands(self, *, limit: int = 5) -> list[str]:
        entries = [entry for entry in self.entries() if entry.kind == "command"]
        recent = list(reversed(entries))[:limit]
        lines: list[str] = []
        for entry in recent:
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            name = payload.get("name", "-")
            status = payload.get("status", "-")
            elapsed = payload.get("elapsed_ms", "-")
            lines.append(f"- ${name}  {status}  {elapsed}ms")
        return lines

    def _query_entries(self, *, after: str | None = None, kinds: Iterable[str] | None = None) -> list[TapeEntry]:
        query = TapeQuery(self._tape, self._store)
        if after is not None:
            query = query.after_anchor(after)
        if kinds:
            query = query.kinds(*kinds)
        return cast(list[TapeEntry], query.all())

    def _append_message(self, payload: dict, *, meta: dict | None = None) -> None:
        meta_payload = dict(meta) if meta else {}
        meta_payload.setdefault("ts", int(time.time()))
        entry = TapeEntry.message(payload, **meta_payload)
        self._store.append(self._tape, entry)


def _entry_text(entry: TapeEntry) -> str:
    if entry.kind == "message":
        payload = entry.payload
        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, str):
                return content
            if content is not None:
                return json.dumps(content, ensure_ascii=False)
        return ""
    return json.dumps(entry.payload, ensure_ascii=False)


def _anchor_name(entry: TapeEntry) -> str:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    name = payload.get("name")
    return str(name or "-")


def _anchor_summary(entry: TapeEntry) -> str:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    state = payload.get("state")
    if isinstance(state, dict):
        summary = state.get("summary")
        return str(summary or "-")
    return "-"


def _format_entry(entry: TapeEntry, text: str) -> str:
    preview = text.strip().replace("\n", " ")
    if len(preview) > ENTRY_PREVIEW_MAX_LEN:
        preview = preview[:ENTRY_PREVIEW_TRUNCATE_LEN] + "..."
    return f"{entry.id:4} {entry.kind} {preview}"


def _format_age(ts: int | None) -> str:
    if ts is None:
        return "unknown"
    delta = max(0, int(time.time() - ts))
    if delta < SECONDS_PER_MINUTE:
        return f"{delta}s ago"
    if delta < SECONDS_PER_HOUR:
        return f"{delta // SECONDS_PER_MINUTE}m ago"
    return f"{delta // SECONDS_PER_HOUR}h ago"
