from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from bub.channels.discord import DiscordChannel


@dataclass
class DummyAuthor:
    id: int = 1
    name: str = "frost"
    global_name: str | None = None


class DummyMessage:
    def __init__(
        self,
        *,
        content: str,
        channel: object,
        author: DummyAuthor | None = None,
    ) -> None:
        self.content = content
        self.channel = channel
        self.author = author or DummyAuthor()
        self.mentions: list[object] = []
        self.reference = None


def _build_channel() -> DiscordChannel:
    settings = SimpleNamespace(
        discord_token="token",  # noqa: S106
        discord_allow_from=[],
        discord_allow_channels=[],
        discord_command_prefix="!",
        discord_proxy=None,
    )
    runtime = SimpleNamespace(settings=settings)
    return DiscordChannel(runtime)  # type: ignore[arg-type]


def test_allow_message_when_content_contains_bub() -> None:
    channel = _build_channel()
    message = DummyMessage(content="please ask Bub to check this", channel=SimpleNamespace(id=100, name="general"))
    assert channel.is_mentioned(message) is True  # type: ignore[arg-type]


def test_allow_message_when_thread_name_starts_with_bub() -> None:
    channel = _build_channel()
    thread = SimpleNamespace(id=101, name="bub-help", parent=SimpleNamespace(name="forum"))
    message = DummyMessage(content="hello", channel=thread)
    assert channel.is_mentioned(message) is True  # type: ignore[arg-type]


def test_reject_message_when_only_parent_name_starts_with_bub() -> None:
    channel = _build_channel()
    thread = SimpleNamespace(id=102, name="question-1", parent=SimpleNamespace(name="bub-forum"))
    message = DummyMessage(content="hello", channel=thread)
    assert channel.is_mentioned(message) is False  # type: ignore[arg-type]


def test_reject_unrelated_message_without_bot_context() -> None:
    channel = _build_channel()
    message = DummyMessage(content="hello world", channel=SimpleNamespace(id=103, name="general"))
    assert channel.is_mentioned(message) is False  # type: ignore[arg-type]


def test_reject_empty_content_even_in_bub_thread() -> None:
    channel = _build_channel()
    thread = SimpleNamespace(id=104, name="bub-help", parent=SimpleNamespace(name="forum"))
    message = DummyMessage(content="   ", channel=thread)
    assert channel.is_mentioned(message) is False  # type: ignore[arg-type]
