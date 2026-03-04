from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bub.channels.discord import DiscordChannel


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


class _DummyAttachment:
    def __init__(
        self,
        *,
        attachment_id: int,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> None:
        self.id = attachment_id
        self.filename = filename
        self.content_type = content_type
        self.size = len(payload)
        self.url = f"https://example.com/{filename}"
        self.width = 20
        self.height = 10
        self._payload = payload

    async def read(self, *, use_cached: bool = False) -> bytes:
        _ = use_cached
        return self._payload


def _build_message(*, content: str, attachments: list[_DummyAttachment]) -> SimpleNamespace:
    author = SimpleNamespace(id=42, name="tester", display_name="Tester", global_name=None)
    return SimpleNamespace(
        id=100,
        content=content,
        attachments=attachments,
        stickers=[],
        author=author,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        channel=SimpleNamespace(id=777),
        guild=SimpleNamespace(id=99),
        reference=None,
    )


@pytest.mark.asyncio
async def test_get_session_prompt_includes_inline_discord_image() -> None:
    channel = _build_channel()
    attachment = _DummyAttachment(
        attachment_id=1,
        filename="img.png",
        content_type="image/png",
        payload=b"abc123",
    )
    message = _build_message(content="please analyze", attachments=[attachment])

    session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]
    data = json.loads(prompt)

    assert session_id == "discord:777"
    assert data["message"] == "please analyze"
    assert data["media"]["attachments"][0]["filename"] == "img.png"
    assert data["media"]["images"][0]["mime_type"] == "image/png"
    assert data["media"]["images"][0]["data_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_get_session_prompt_formats_attachment_only_message() -> None:
    channel = _build_channel()
    attachment = _DummyAttachment(
        attachment_id=1,
        filename="img.png",
        content_type="image/png",
        payload=b"abc123",
    )
    message = _build_message(content="", attachments=[attachment])

    _session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]
    data = json.loads(prompt)

    assert data["message"] == "[Attachment: img.png]"
    assert data["media"]["images"][0]["data_url"].startswith("data:image/png;base64,")
