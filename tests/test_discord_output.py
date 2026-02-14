from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from bub.channels.discord import DiscordChannel
from bub.core.agent_loop import LoopResult


class DummyMessageable:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        self.sent.append(kwargs)


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


@pytest.mark.asyncio
async def test_process_output_sends_only_immediate_and_prints_full(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _build_channel()
    sink = DummyMessageable()
    printed: list[str] = []

    def _capture_print(*args: object, **kwargs: object) -> None:
        printed.append(" ".join(str(arg) for arg in args))

    async def _resolve_channel(_session_id: str) -> DummyMessageable:
        return sink

    monkeypatch.setattr(builtins, "print", _capture_print)
    channel._bot = object()  # type: ignore[assignment]
    channel._resolve_channel = _resolve_channel  # type: ignore[method-assign]

    output = LoopResult(
        immediate_output="immediate reply",
        assistant_output="assistant details",
        exit_requested=False,
        steps=1,
        error="boom",
    )
    await channel.process_output("discord:1", output)

    joined = "\n".join(printed)
    assert "immediate reply" in joined
    assert "assistant details" in joined
    assert "Error: boom" in joined
    assert sink.sent == [{"content": "immediate reply"}]


@pytest.mark.asyncio
async def test_process_output_no_immediate_does_not_send_but_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _build_channel()
    sink = DummyMessageable()
    printed: list[str] = []

    def _capture_print(*args: object, **kwargs: object) -> None:
        printed.append(" ".join(str(arg) for arg in args))

    async def _resolve_channel(_session_id: str) -> DummyMessageable:
        return sink

    monkeypatch.setattr(builtins, "print", _capture_print)
    channel._bot = object()  # type: ignore[assignment]
    channel._resolve_channel = _resolve_channel  # type: ignore[method-assign]

    output = LoopResult(
        immediate_output="",
        assistant_output="assistant only",
        exit_requested=False,
        steps=1,
        error=None,
    )
    await channel.process_output("discord:1", output)

    joined = "\n".join(printed)
    assert "assistant only" in joined
    assert sink.sent == []
