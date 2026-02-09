"""Context building for tape entries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

from republic.core.errors import ErrorKind
from republic.core.results import ErrorPayload
from republic.tape.entries import TapeEntry


class _LastAnchor:
    def __repr__(self) -> str:
        return "LAST_ANCHOR"


LAST_ANCHOR = _LastAnchor()
AnchorSelector: TypeAlias = str | None | _LastAnchor


@dataclass(frozen=True)
class TapeContext:
    """Rules for selecting tape entries into a prompt context.

    anchor: LAST_ANCHOR for the most recent anchor, None for the full tape, or an anchor name.
    select: Optional selector called after anchor slicing that returns messages.
    """

    anchor: AnchorSelector = LAST_ANCHOR
    select: Callable[[Sequence[TapeEntry], TapeContext], list[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class ContextSelection:
    messages: list[dict[str, Any]]
    error: ErrorPayload | None = None


def build_messages(entries: Sequence[TapeEntry], context: TapeContext) -> ContextSelection:
    selected_entries, error = _slice_after_anchor(entries, context.anchor)
    if context.select is not None:
        return ContextSelection(context.select(selected_entries, context), error=error)
    return ContextSelection(_default_messages(selected_entries), error=error)


def _default_messages(entries: Sequence[TapeEntry]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in entries:
        if entry.kind != "message":
            continue
        payload = entry.payload
        if not isinstance(payload, dict):
            continue
        messages.append(dict(payload))
    return messages


def _slice_after_anchor(
    entries: Sequence[TapeEntry],
    anchor: AnchorSelector,
) -> tuple[Sequence[TapeEntry], ErrorPayload | None]:
    if anchor is None:
        return entries, None

    anchor_name = None if anchor is LAST_ANCHOR else anchor
    start_index = 0
    found = False
    for idx in range(len(entries) - 1, -1, -1):
        entry = entries[idx]
        if entry.kind != "anchor":
            continue
        if anchor_name is not None and entry.payload.get("name") != anchor_name:
            continue
        start_index = idx + 1
        found = True
        break

    if not found:
        if anchor_name is None:
            return (), ErrorPayload(ErrorKind.NOT_FOUND, "No anchors found in tape.")
        return (), ErrorPayload(
            ErrorKind.NOT_FOUND,
            f"Anchor '{anchor_name}' was not found.",
            details={"anchor": anchor_name},
        )

    return entries[start_index:], None
