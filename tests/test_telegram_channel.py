from __future__ import annotations

from types import SimpleNamespace

import pytest

from bub.channels.bus import MessageBus
from bub.channels.telegram import TelegramChannel, TelegramConfig


class DummyMessage:
    def __init__(self, *, chat_id: int, text: str, message_id: int = 1) -> None:
        self.chat_id = chat_id
        self.text = text
        self.message_id = message_id
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


@pytest.mark.asyncio
async def test_on_text_denies_chat_not_in_allowlist() -> None:
    channel = TelegramChannel(
        MessageBus(),
        TelegramConfig(token="t", allow_from=set(), allow_chats={"123"}),  # noqa: S106
    )
    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )
    published: list[object] = []

    async def _publish_inbound(msg: object) -> None:
        published.append(msg)

    channel.publish_inbound = _publish_inbound  # type: ignore[method-assign]

    await channel._on_text(update, None)  # type: ignore[arg-type]
    assert published == []


@pytest.mark.asyncio
async def test_on_text_allows_chat_in_allowlist() -> None:
    channel = TelegramChannel(
        MessageBus(),
        TelegramConfig(token="t", allow_from=set(), allow_chats={"999"}),  # noqa: S106
    )
    channel._start_typing = lambda _chat_id: None  # type: ignore[method-assign]
    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )
    published: list[object] = []

    async def _publish_inbound(msg: object) -> None:
        published.append(msg)

    channel.publish_inbound = _publish_inbound  # type: ignore[method-assign]

    await channel._on_text(update, None)  # type: ignore[arg-type]

    assert message.replies == []
    assert len(published) == 1


@pytest.mark.asyncio
async def test_on_text_stops_typing_when_publish_fails() -> None:
    channel = TelegramChannel(
        MessageBus(),
        TelegramConfig(token="t", allow_from=set(), allow_chats={"999"}),  # noqa: S106
    )
    calls = {"start": 0, "stop": 0}

    def _start_typing(_chat_id: str) -> None:
        calls["start"] += 1

    def _stop_typing(_chat_id: str) -> None:
        calls["stop"] += 1

    channel._start_typing = _start_typing  # type: ignore[method-assign]
    channel._stop_typing = _stop_typing  # type: ignore[method-assign]

    async def _publish_inbound(_msg: object) -> None:
        raise RuntimeError("publish failed")

    channel.publish_inbound = _publish_inbound  # type: ignore[method-assign]
    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )

    with pytest.raises(RuntimeError, match="publish failed"):
        await channel._on_text(update, None)  # type: ignore[arg-type]

    assert calls == {"start": 1, "stop": 1}
