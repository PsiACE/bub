from __future__ import annotations

import asyncio

import pytest

from bub.channels.base import BaseChannel
from bub.channels.manager import ChannelManager


class _Settings:
    telegram_enabled = False
    discord_enabled = False


class _Runtime:
    settings = _Settings()

    def install_hooks(self, manager: ChannelManager) -> None:
        pass


class _FakeChannel(BaseChannel[object]):
    name = "fake"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self.started = asyncio.Event()
        self.stopped = False

    async def start(self, on_receive):  # type: ignore[override]
        _ = on_receive
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped = True

    async def get_session_prompt(self, message: object) -> tuple[str, str]:
        _ = message
        return "session", "prompt"

    async def process_output(self, session_id: str, output) -> None:
        _ = (session_id, output)


@pytest.mark.asyncio
async def test_channel_manager_starts_and_stops_registered_channels() -> None:
    manager = ChannelManager(_Runtime())  # type: ignore[arg-type]
    manager.register(_FakeChannel)

    task = asyncio.create_task(manager.run())
    channel = manager.channels["fake"]
    await asyncio.wait_for(channel.started.wait(), timeout=1.0)
    assert manager.enabled_channels() == ["fake"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    assert channel.stopped is True
