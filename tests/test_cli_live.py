"""Tests for CLI live rendering behavior."""

from __future__ import annotations

from dataclasses import dataclass, field

from republic.tape.entries import TapeEntry

from bub.cli.live import _render_message


@dataclass
class _FakeRenderer:
    user_messages: list[str] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)
    info_messages: list[str] = field(default_factory=list)

    def user_message(self, message: str) -> None:
        self.user_messages.append(message)

    def assistant_message(self, message: str) -> None:
        self.assistant_messages.append(message)

    def info(self, message: str) -> None:
        self.info_messages.append(message)


def test_render_message_does_not_echo_user_input() -> None:
    renderer = _FakeRenderer()
    entry = TapeEntry(
        1,
        "message",
        {"role": "user", "content": "hello"},
        {"lane": "main", "view": True},
    )

    _render_message(entry, renderer)

    assert renderer.user_messages == []
    assert renderer.assistant_messages == []
    assert renderer.info_messages == []


def test_render_message_strips_done_from_assistant_output() -> None:
    renderer = _FakeRenderer()
    entry = TapeEntry(
        1,
        "message",
        {"role": "assistant", "content": "done text\n$done"},
        {"lane": "main", "view": True},
    )

    _render_message(entry, renderer)

    assert renderer.assistant_messages == ["done text"]
