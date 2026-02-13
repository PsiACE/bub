from __future__ import annotations

from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

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


class DummyBot:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.fail_first and len(self.calls) == 1:
            raise BadRequest("Can't parse entities: unmatched end tag")


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


@pytest.mark.asyncio
async def test_send_falls_back_to_plain_text_when_entity_parse_fails() -> None:
    channel = TelegramChannel(
        MessageBus(),
        TelegramConfig(token="t", allow_from=set(), allow_chats=set()),  # noqa: S106
    )
    bot = DummyBot(fail_first=True)
    channel._app = SimpleNamespace(bot=bot)

    outbound = SimpleNamespace(chat_id="123", content="a < b", reply_to_message_id=7)
    await channel.send(outbound)  # type: ignore[arg-type]

    assert len(bot.calls) == 2
    assert bot.calls[0]["parse_mode"] == "MarkdownV2"
    assert bot.calls[1]["parse_mode"] is None
    assert bot.calls[1]["text"] == "a &lt; b"
    assert bot.calls[1]["reply_to_message_id"] == 7


@pytest.mark.asyncio
async def test_send_uses_markdownv2_for_long_message() -> None:
    channel = TelegramChannel(
        MessageBus(),
        TelegramConfig(token="t", allow_from=set(), allow_chats=set()),  # noqa: S106
    )
    bot = DummyBot()
    channel._app = SimpleNamespace(bot=bot)

    outbound = SimpleNamespace(chat_id="123", content="x" * 300, reply_to_message_id=None)
    await channel.send(outbound)  # type: ignore[arg-type]

    assert len(bot.calls) == 1
    assert bot.calls[0]["parse_mode"] == "MarkdownV2"
