from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bub.channels.telegram import TelegramChannel


def _build_channel() -> TelegramChannel:
    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            telegram_token="token",  # noqa: S106
            telegram_allow_from=[],
            telegram_allow_chats=[],
            telegram_proxy=None,
        )
    )
    return TelegramChannel(runtime)


def _build_message(*, text: str = "hello", chat_id: int = 123, message_id: int = 10) -> SimpleNamespace:
    user = SimpleNamespace(id=42, username="tester", full_name="Test User", is_bot=False)
    return SimpleNamespace(
        chat_id=chat_id,
        chat=SimpleNamespace(type="private"),
        message_id=message_id,
        text=text,
        caption=None,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        from_user=user,
        reply_to_message=None,
        photo=None,
        audio=None,
        sticker=None,
        video=None,
        voice=None,
        document=None,
        video_note=None,
    )


class _DummyTelegramFile:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._data)


class _DummyBot:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def get_file(self, _file_id: str) -> _DummyTelegramFile:
        return _DummyTelegramFile(self._data)


@pytest.mark.asyncio
async def test_get_session_prompt_wraps_text_with_notice_and_metadata() -> None:
    channel = _build_channel()
    message = _build_message(text="hello world")

    session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]

    assert session_id == "telegram:123"
    data = json.loads(prompt)
    assert data["message"] == "hello world"
    assert data["chat_id"] == "123"
    assert data["message_id"] == 10
    assert data["type"] == "text"
    assert data["sender_id"] == "42"
    assert data["sender_is_bot"] is False


@pytest.mark.asyncio
async def test_get_session_prompt_returns_raw_for_comma_command() -> None:
    channel = _build_channel()
    message = _build_message(text=",status")

    session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]

    assert session_id == "telegram:123"
    assert prompt == ",status"


@pytest.mark.asyncio
async def test_get_session_prompt_includes_reply_metadata() -> None:
    channel = _build_channel()
    message = _build_message(text="replying")
    message.reply_to_message = SimpleNamespace(
        message_id=99,
        text="original",
        from_user=SimpleNamespace(id=1000, username="bot", is_bot=True),
    )

    _session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]
    data = json.loads(prompt)
    reply = data["reply_to_message"]
    assert reply["message_id"] == 99
    assert reply["from_user_id"] == 1000
    assert reply["from_username"] == "bot"
    assert reply["from_is_bot"] is True


@pytest.mark.asyncio
async def test_get_session_prompt_includes_inline_photo_image() -> None:
    channel = _build_channel()
    message = _build_message(text="")
    message.text = None
    message.caption = "look"
    message.photo = [
        SimpleNamespace(file_id="small", file_size=5, width=10, height=10),
        SimpleNamespace(file_id="large", file_size=6, width=20, height=20),
    ]
    message.get_bot = lambda: _DummyBot(b"abcdef")  # type: ignore[assignment]

    _session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]
    data = json.loads(prompt)

    assert data["type"] == "photo"
    assert data["media"]["file_id"] == "large"
    assert data["media"]["images"][0]["id"] == "large"
    assert data["media"]["images"][0]["mime_type"] == "image/jpeg"
    assert data["media"]["images"][0]["data_url"].startswith("data:image/jpeg;base64,")
