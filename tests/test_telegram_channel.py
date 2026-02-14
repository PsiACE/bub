from __future__ import annotations

from types import SimpleNamespace

import pytest

from bub.channels.telegram import TelegramChannel


class _Settings:
    def __init__(self) -> None:
        self.telegram_token = "test-token"  # noqa: S105
        self.telegram_allow_from: list[str] = []
        self.telegram_allow_chats: list[str] = []


class _Runtime:
    def __init__(self) -> None:
        self.settings = _Settings()


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
    runtime = _Runtime()
    runtime.settings.telegram_allow_chats = ["123"]
    channel = TelegramChannel(runtime)  # type: ignore[arg-type]

    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )

    await channel._on_text(update, None)  # type: ignore[arg-type]
    assert message.replies == []


@pytest.mark.asyncio
async def test_on_text_invokes_receive_handler_for_allowed_message() -> None:
    runtime = _Runtime()
    runtime.settings.telegram_allow_chats = ["999"]
    channel = TelegramChannel(runtime)  # type: ignore[arg-type]

    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )

    received: list[object] = []

    async def _on_receive(msg: object) -> None:
        received.append(msg)

    channel._on_receive = _on_receive

    async def _start_typing(_chat_id: str) -> None:
        return None

    async def _stop_typing(_chat_id: str) -> None:
        return None

    channel._start_typing = _start_typing  # type: ignore[method-assign]
    channel._stop_typing = _stop_typing  # type: ignore[method-assign]

    await channel._on_text(update, None)  # type: ignore[arg-type]

    assert message.replies == []
    assert received == [message]


@pytest.mark.asyncio
async def test_on_text_always_stops_typing() -> None:
    runtime = _Runtime()
    runtime.settings.telegram_allow_chats = ["999"]
    channel = TelegramChannel(runtime)  # type: ignore[arg-type]

    message = DummyMessage(chat_id=999, text="hello")
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=1, username="tester", full_name="Test User"),
    )

    calls = {"start": 0, "stop": 0}

    async def _start_typing(_chat_id: str) -> None:
        calls["start"] += 1

    async def _stop_typing(_chat_id: str) -> None:
        calls["stop"] += 1

    async def _on_receive(_msg: object) -> None:
        raise RuntimeError("receive failed")

    channel._on_receive = _on_receive
    channel._start_typing = _start_typing  # type: ignore[method-assign]
    channel._stop_typing = _stop_typing  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="receive failed"):
        await channel._on_text(update, None)  # type: ignore[arg-type]

    assert calls == {"start": 1, "stop": 1}
