"""Tests for image/media message handling through the pipeline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bub.builtin.hook_impl import BuiltinImpl
from bub.channels.message import ChannelMessage, MediaItem
from bub.channels.telegram import TelegramChannel, _extract_media_items
from bub.framework import BubFramework

# ---------------------------------------------------------------------------
# MediaItem & ChannelMessage
# ---------------------------------------------------------------------------


def test_media_item_is_frozen() -> None:
    item = MediaItem(type="image", data=b"abc", mime_type="image/jpeg")
    with pytest.raises(AttributeError):
        item.type = "video"  # type: ignore[misc]


def test_media_item_data_url_property() -> None:
    item = MediaItem(type="image", data=b"\x89PNG", mime_type="image/png")
    assert item.data_url.startswith("data:image/png;base64,")
    assert item.encoded_data in item.data_url


def test_channel_message_from_batch_merges_media() -> None:
    m1 = ChannelMessage(
        session_id="s",
        channel="tg",
        content="a",
        media=[MediaItem(type="image", data=b"AAA", mime_type="image/jpeg")],
    )
    m2 = ChannelMessage(
        session_id="s",
        channel="tg",
        content="b",
        media=[MediaItem(type="image", data=b"BBB", mime_type="image/jpeg")],
    )
    merged = ChannelMessage.from_batch([m1, m2])

    assert merged.content == "a\nb"
    assert len(merged.media) == 2
    assert merged.media[0].data == b"AAA"
    assert merged.media[1].data == b"BBB"


def test_channel_message_from_batch_no_media() -> None:
    m1 = ChannelMessage(session_id="s", channel="tg", content="a")
    m2 = ChannelMessage(session_id="s", channel="tg", content="b")
    merged = ChannelMessage.from_batch([m1, m2])

    assert merged.media == []


# ---------------------------------------------------------------------------
# _extract_media_items
# ---------------------------------------------------------------------------


def test_extract_media_items_from_photo_metadata() -> None:
    metadata = {
        "type": "photo",
        "media": {
            "file_id": "abc",
            "data": b"\xff\xd8\xff\xe0",
            "mime_type": "image/jpeg",
            "width": 800,
            "height": 600,
        },
    }
    items = _extract_media_items(metadata)

    assert len(items) == 1
    assert items[0].type == "image"
    assert items[0].data == b"\xff\xd8\xff\xe0"
    assert items[0].mime_type == "image/jpeg"
    # data should be removed from the original dict
    assert "data" not in metadata["media"]


def test_extract_media_items_from_sticker_metadata() -> None:
    metadata = {
        "type": "sticker",
        "media": {
            "file_id": "stk",
            "data": b"RIFF",
            "mime_type": "image/webp",
        },
    }
    items = _extract_media_items(metadata)

    assert len(items) == 1
    assert items[0].type == "image"


def test_extract_media_items_from_audio_metadata() -> None:
    metadata = {
        "type": "audio",
        "media": {
            "file_id": "aud",
            "data": b"\xff\xfb",
            "mime_type": "audio/mpeg",
        },
    }
    items = _extract_media_items(metadata)

    assert len(items) == 1
    assert items[0].type == "audio"


def test_extract_media_items_from_video_metadata() -> None:
    metadata = {
        "type": "video",
        "media": {
            "file_id": "vid",
            "data": b"\x00\x00\x00",
            "mime_type": "video/mp4",
        },
    }
    items = _extract_media_items(metadata)

    assert len(items) == 1
    assert items[0].type == "video"


def test_extract_media_items_from_document_metadata() -> None:
    metadata = {
        "type": "document",
        "media": {
            "file_id": "doc",
            "data": b"%PDF",
            "mime_type": "application/pdf",
        },
    }
    items = _extract_media_items(metadata)

    assert len(items) == 1
    assert items[0].type == "document"


def test_extract_media_items_returns_empty_when_no_media() -> None:
    assert _extract_media_items({"type": "text"}) == []


def test_extract_media_items_returns_empty_when_media_is_none() -> None:
    assert _extract_media_items({"type": "photo", "media": None}) == []


def test_extract_media_items_returns_empty_when_no_data() -> None:
    metadata = {"type": "photo", "media": {"file_id": "abc", "width": 800}}
    assert _extract_media_items(metadata) == []


def test_extract_media_items_unknown_type_defaults_to_document() -> None:
    metadata = {
        "type": "unknown_new_thing",
        "media": {"data": b"\x00", "mime_type": "foo/bar"},
    }
    items = _extract_media_items(metadata)

    assert items[0].type == "document"


# ---------------------------------------------------------------------------
# TelegramChannel._build_message with media
# ---------------------------------------------------------------------------


def _async_return(value):
    async def runner(*args, **kwargs):
        return value

    return runner


@pytest.mark.asyncio
async def test_telegram_build_message_extracts_media_items(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = TelegramChannel(lambda message: None)  # type: ignore[arg-type]
    photo_metadata = {
        "type": "photo",
        "sender_id": "7",
        "media": {
            "file_id": "f1",
            "data": b"\xff\xd8\xff\xe0",
            "mime_type": "image/jpeg",
        },
    }
    channel._parser = SimpleNamespace(  # type: ignore[assignment]
        parse=_async_return(("[Photo message]", photo_metadata)),
        get_reply=_async_return(None),
    )
    monkeypatch.setattr("bub.channels.telegram.MESSAGE_FILTER.filter", lambda message: True)

    message = SimpleNamespace(chat_id=42)
    result = await channel._build_message(message)  # type: ignore[arg-type]

    assert len(result.media) == 1
    assert result.media[0].type == "image"
    assert result.media[0].data == b"\xff\xd8\xff\xe0"


@pytest.mark.asyncio
async def test_telegram_build_message_no_media_for_text(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = TelegramChannel(lambda message: None)  # type: ignore[arg-type]
    channel._parser = SimpleNamespace(  # type: ignore[assignment]
        parse=_async_return(("hello", {"type": "text", "sender_id": "7"})),
        get_reply=_async_return(None),
    )
    monkeypatch.setattr("bub.channels.telegram.MESSAGE_FILTER.filter", lambda message: True)

    message = SimpleNamespace(chat_id=42)
    result = await channel._build_message(message)  # type: ignore[arg-type]

    assert result.media == []


# ---------------------------------------------------------------------------
# build_prompt with media
# ---------------------------------------------------------------------------


class FakeAgent:
    def __init__(self, home: Path) -> None:
        self.settings = SimpleNamespace(home=home)


def _build_impl(tmp_path: Path) -> tuple[BubFramework, BuiltinImpl]:
    framework = BubFramework()
    impl = BuiltinImpl(framework)
    impl.agent = FakeAgent(tmp_path)  # type: ignore[assignment]
    return framework, impl


def test_build_prompt_returns_string_without_media(tmp_path: Path) -> None:
    _, impl = _build_impl(tmp_path)
    message = ChannelMessage(session_id="s", channel="tg", content="hello")

    result = impl.build_prompt(message, session_id="s", state={})

    assert isinstance(result, str)
    assert "hello" in result


def test_build_prompt_returns_multimodal_parts_with_image_media(tmp_path: Path) -> None:
    _, impl = _build_impl(tmp_path)
    message = ChannelMessage(
        session_id="s",
        channel="tg",
        content="describe this",
        media=[MediaItem(type="image", data=b"\xff\xd8", mime_type="image/jpeg")],
    )

    result = impl.build_prompt(message, session_id="s", state={})

    assert isinstance(result, list)
    assert len(result) == 2

    text_part = result[0]
    assert text_part["type"] == "text"
    assert "describe this" in text_part["text"]

    image_part = result[1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_build_prompt_with_multiple_images(tmp_path: Path) -> None:
    _, impl = _build_impl(tmp_path)
    message = ChannelMessage(
        session_id="s",
        channel="tg",
        content="compare these",
        media=[
            MediaItem(type="image", data=b"A", mime_type="image/jpeg"),
            MediaItem(type="image", data=b"B", mime_type="image/jpeg"),
        ],
    )

    result = impl.build_prompt(message, session_id="s", state={})

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[1]["type"] == "image_url"
    assert result[2]["type"] == "image_url"


def test_build_prompt_with_non_image_media_only_includes_text(tmp_path: Path) -> None:
    _, impl = _build_impl(tmp_path)
    message = ChannelMessage(
        session_id="s",
        channel="tg",
        content="listen to this",
        media=[MediaItem(type="audio", data=b"\xff\xfb", mime_type="audio/ogg")],
    )

    result = impl.build_prompt(message, session_id="s", state={})

    # Non-image media: still returns a list but only with text part
    assert isinstance(result, list)
    text_parts = [p for p in result if p["type"] == "text"]
    image_parts = [p for p in result if p["type"] == "image_url"]
    assert len(text_parts) == 1
    assert len(image_parts) == 0


def test_build_prompt_command_ignores_media(tmp_path: Path) -> None:
    _, impl = _build_impl(tmp_path)
    message = ChannelMessage(
        session_id="s",
        channel="tg",
        content=",help",
        media=[MediaItem(type="image", data=b"X", mime_type="image/jpeg")],
    )

    result = impl.build_prompt(message, session_id="s", state={})

    assert isinstance(result, str)
    assert result == ",help"
    assert message.kind == "command"


# ---------------------------------------------------------------------------
# _extract_text_from_parts
# ---------------------------------------------------------------------------


def test_extract_text_from_parts() -> None:
    from bub.builtin.agent import _extract_text_from_parts

    parts = [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,X"}},
        {"type": "text", "text": "world"},
    ]
    assert _extract_text_from_parts(parts) == "hello\nworld"


def test_extract_text_from_parts_empty() -> None:
    from bub.builtin.agent import _extract_text_from_parts

    assert _extract_text_from_parts([]) == ""


def test_extract_text_from_parts_no_text_parts() -> None:
    from bub.builtin.agent import _extract_text_from_parts

    parts = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,X"}}]
    assert _extract_text_from_parts(parts) == ""
