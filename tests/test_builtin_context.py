from __future__ import annotations

import pytest

from bub.builtin.context import TapeContext, build_messages
from bub.runtime import BubError, ErrorKind
from bub.tape import TapeEntry


def message_entry(content: str) -> TapeEntry:
    return TapeEntry(id=0, kind="message", payload={"role": "user", "content": content})


def anchor_entry(name: str) -> TapeEntry:
    return TapeEntry(id=0, kind="anchor", payload={"name": name})


def test_tape_context_defaults_to_entries_after_latest_anchor() -> None:
    entries = [
        message_entry("old"),
        anchor_entry("phase-1"),
        message_entry("new"),
    ]

    assert build_messages(entries, TapeContext()) == [{"role": "user", "content": "new"}]


def test_tape_context_anchor_none_selects_all_entries() -> None:
    entries = [
        message_entry("old"),
        anchor_entry("phase-1"),
        message_entry("new"),
    ]

    assert build_messages(entries, TapeContext(anchor=None)) == [
        {"role": "user", "content": "old"},
        {"role": "user", "content": "new"},
    ]


def test_tape_context_can_select_entries_after_named_anchor() -> None:
    entries = [
        anchor_entry("phase-1"),
        message_entry("old"),
        anchor_entry("phase-2"),
        message_entry("new"),
    ]

    assert build_messages(entries, TapeContext(anchor="phase-2")) == [{"role": "user", "content": "new"}]


def test_tape_context_missing_anchor_raises_not_found() -> None:
    with pytest.raises(BubError) as exc_info:
        build_messages([message_entry("old")], TapeContext())

    assert exc_info.value.kind is ErrorKind.NOT_FOUND
