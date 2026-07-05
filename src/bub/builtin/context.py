"""Tape context helpers."""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from bub.runtime import BubError, ErrorKind
from bub.tape import TapeEntry


class _LastAnchor:
    def __repr__(self) -> str:
        return "LAST_ANCHOR"


LAST_ANCHOR = _LastAnchor()
type AnchorSelector = str | None | _LastAnchor
type SelectedMessages = list[dict[str, Any]] | Coroutine[Any, Any, list[dict[str, Any]]]
type ContextSelector = Callable[[Iterable[TapeEntry], "TapeContext"], SelectedMessages]


@dataclass(frozen=True)
class TapeContext:
    """Rules for selecting builtin tape entries into a model prompt."""

    anchor: AnchorSelector = LAST_ANCHOR
    select: ContextSelector | None = None
    state: dict[str, Any] = field(default_factory=dict)


def default_tape_context() -> TapeContext:
    """Return the default context selection for Bub."""

    return TapeContext(select=_select_messages)


def build_messages(entries: Iterable[TapeEntry], context: TapeContext) -> SelectedMessages:
    selected_entries = _select_anchor_window(list(entries), context.anchor)
    if context.select is not None:
        return context.select(selected_entries, context)
    return _default_messages(selected_entries)


def _default_messages(entries: Iterable[TapeEntry]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in entries:
        if entry.kind != "message":
            continue
        payload = entry.payload
        if isinstance(payload, dict):
            messages.append(dict(payload))
    return messages


def _select_anchor_window(entries: Sequence[TapeEntry], anchor: AnchorSelector) -> list[TapeEntry]:
    if anchor is None:
        return list(entries)
    if isinstance(anchor, _LastAnchor):
        anchor_index = _anchor_index(entries, None)
        if anchor_index < 0:
            raise BubError(ErrorKind.NOT_FOUND, "No anchors found in tape.")
        return list(entries[anchor_index + 1 :])
    if not anchor:
        return list(entries)
    anchor_index = _anchor_index(entries, anchor)
    if anchor_index < 0:
        raise BubError(ErrorKind.NOT_FOUND, f"Anchor '{anchor}' was not found.")
    return list(entries[anchor_index + 1 :])


def _anchor_index(entries: Sequence[TapeEntry], name: str | None) -> int:
    for idx in range(len(entries) - 1, -1, -1):
        entry = entries[idx]
        if entry.kind != "anchor":
            continue
        if name is not None and entry.payload.get("name") != name:
            continue
        return idx
    return -1


def _select_messages(entries: Iterable[TapeEntry], _context: TapeContext) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    pending_calls: list[dict[str, Any]] = []

    for entry in entries:
        match entry.kind:
            case "anchor":
                _append_anchor_entry(messages, entry)
            case "message":
                _append_message_entry(messages, entry)
            case "tool_call":
                pending_calls = _append_tool_call_entry(messages, entry)
            case "tool_result":
                _append_tool_result_entry(messages, pending_calls, entry)
                pending_calls = []
    return messages


def _append_anchor_entry(messages: list[dict[str, Any]], entry: TapeEntry) -> None:
    payload = entry.payload
    content = f"[Anchor created: {payload.get('name')}]: {json.dumps(payload.get('state'), ensure_ascii=False)}"
    messages.append({"role": "assistant", "content": content})


def _append_message_entry(messages: list[dict[str, Any]], entry: TapeEntry) -> None:
    payload = entry.payload
    if isinstance(payload, dict):
        messages.append(dict(payload))


def _append_tool_call_entry(messages: list[dict[str, Any]], entry: TapeEntry) -> list[dict[str, Any]]:
    calls = _normalize_tool_calls(entry.payload.get("calls"))
    if calls:
        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
    return calls


def _append_tool_result_entry(
    messages: list[dict[str, Any]],
    pending_calls: list[dict[str, Any]],
    entry: TapeEntry,
) -> None:
    results = entry.payload.get("results")
    if not isinstance(results, list):
        return
    for index, result in enumerate(results):
        messages.append(_build_tool_result_message(result, pending_calls, index))


def _build_tool_result_message(
    result: object,
    pending_calls: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "tool", "content": _render_tool_result(result)}
    if index >= len(pending_calls):
        return message

    call = pending_calls[index]
    call_id = call.get("id")
    if isinstance(call_id, str) and call_id:
        message["tool_call_id"] = call_id

    function = call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str) and name:
            message["name"] = name
    return message


def _normalize_tool_calls(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            calls.append(dict(item))
    return calls


def _render_tool_result(result: object) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except TypeError:
        return str(result)
