from __future__ import annotations

from republic.core.errors import ErrorKind
from republic.tape.context import LAST_ANCHOR, TapeContext, build_messages
from republic.tape.entries import TapeEntry
from republic.tape.query import TapeQuery
from republic.tape.store import InMemoryTapeStore


def _seed_entries() -> list[TapeEntry]:
    return [
        TapeEntry.message({"role": "user", "content": "before"}),
        TapeEntry.anchor("a1"),
        TapeEntry.message({"role": "user", "content": "task 1"}),
        TapeEntry.message({"role": "assistant", "content": "answer 1"}),
        TapeEntry.anchor("a2"),
        TapeEntry.message({"role": "user", "content": "task 2"}),
    ]


def test_build_messages_uses_last_anchor_slice() -> None:
    selection = build_messages(_seed_entries(), TapeContext(anchor=LAST_ANCHOR))
    assert selection.error is None
    assert [message["content"] for message in selection.messages] == ["task 2"]


def test_build_messages_reports_missing_anchor() -> None:
    selection = build_messages(_seed_entries(), TapeContext(anchor="missing"))
    assert selection.messages == []
    assert selection.error is not None
    assert selection.error.kind == ErrorKind.NOT_FOUND


def test_query_between_anchors_and_limit() -> None:
    store = InMemoryTapeStore()
    tape = "session"

    for entry in _seed_entries():
        store.append(tape, entry)

    result = TapeQuery(tape=tape, store=store).between_anchors("a1", "a2").kinds("message").limit(1).all()
    assert result.error is None
    assert len(result.entries) == 1
    assert result.entries[0].payload["content"] == "task 1"
