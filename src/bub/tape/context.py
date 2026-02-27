"""Tape context helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from republic import TapeContext, TapeEntry


def default_tape_context(state: dict[str, Any] | None = None) -> TapeContext:
    """Return the default context selection for Bub."""

    return TapeContext(select=_select_messages, state=state or {})


def _select_messages(entries: Iterable[TapeEntry], _context: TapeContext) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    pending_calls: list[dict[str, Any]] = []

    for entry in entries:
        if entry.kind == "message":
            _append_message_entry(messages, entry)
            continue

        if entry.kind == "tool_call":
            pending_calls = _append_tool_call_entry(messages, entry)
            continue

        if entry.kind == "tool_result":
            _append_tool_result_entry(messages, pending_calls, entry)
            pending_calls = []

    return messages


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
    if not isinstance(results, list) or not pending_calls:
        return
    paired_count = min(len(results), len(pending_calls))
    if paired_count <= 0:
        return
    if paired_count < len(pending_calls):
        _trim_last_tool_call_message(messages, paired_count)
        pending_calls = pending_calls[:paired_count]
    for index, result in enumerate(results[:paired_count]):
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


def _trim_last_tool_call_message(messages: list[dict[str, Any]], count: int) -> None:
    if not messages:
        return
    candidate = messages[-1]
    if candidate.get("role") != "assistant":
        return
    tool_calls = candidate.get("tool_calls")
    if not isinstance(tool_calls, list):
        return
    if count <= 0:
        messages.pop()
        return
    candidate["tool_calls"] = tool_calls[:count]


def _normalize_tool_calls(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in value:
        calls.extend(_normalize_tool_call(item))
    return calls


def _normalize_tool_call(item: object) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []

    normalized = dict(item)
    function = normalized.get("function")
    if not isinstance(function, dict):
        return []

    name = function.get("name")
    if not isinstance(name, str) or not name:
        return []

    raw_arguments = function.get("arguments")
    argument_chunks = _normalize_tool_arguments(raw_arguments)
    if not argument_chunks:
        return []

    call_id = normalized.get("id")
    calls: list[dict[str, Any]] = []
    for index, arguments in enumerate(argument_chunks):
        cloned = dict(normalized)
        cloned_function = dict(function)
        cloned_function["arguments"] = arguments
        cloned["function"] = cloned_function
        if isinstance(call_id, str) and call_id and index > 0:
            cloned["id"] = f"{call_id}__{index + 1}"
        calls.append(cloned)
    return calls


def _normalize_tool_arguments(value: object) -> list[str]:
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False)]
    if not isinstance(value, str):
        return []

    raw = value.strip()
    if not raw:
        return []

    parsed = _parse_json_object(raw)
    if parsed is not None:
        return [raw]

    chunks = _split_json_objects(raw)
    if len(chunks) <= 1:
        return []
    return chunks


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _split_json_objects(raw: str) -> list[str]:
    decoder = json.JSONDecoder()
    chunks: list[str] = []
    position = 0
    total = len(raw)
    while position < total:
        while position < total and raw[position].isspace():
            position += 1
        if position >= total:
            break
        try:
            parsed, end = decoder.raw_decode(raw, position)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, dict):
            return []
        chunks.append(raw[position:end])
        position = end
    return chunks


def _render_tool_result(result: object) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except TypeError:
        return str(result)
