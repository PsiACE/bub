import asyncio
import contextlib

import pytest

from bub.channels.base import BaseChannel
from bub.channels.manager import ChannelManager
from bub.cli.app import _serve_channels


class _Settings:
    telegram_enabled = False
    discord_enabled = False


class _Runtime:
    settings = _Settings()


class _ChannelRaisesOnStop(BaseChannel[object]):
    name = "bad"

    async def start(self, on_receive):  # type: ignore[override]
        _ = on_receive
        try:
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("stop failure")

    async def get_session_prompt(self, message: object) -> tuple[str, str]:
        _ = message
        return "s", "p"

    async def process_output(self, session_id: str, output):
        _ = (session_id, output)


@pytest.mark.asyncio
async def test_channel_manager_shutdown_propagates_channel_stop_error() -> None:
    manager = ChannelManager(_Runtime())  # type: ignore[arg-type]
    manager.register(_ChannelRaisesOnStop)

    task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(RuntimeError, match="stop failure"):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_serve_channels_handles_cancelled_error_from_graceful_shutdown() -> None:
    class _DummyRuntime:
        @contextlib.asynccontextmanager
        async def graceful_shutdown(self):
            stop_event = asyncio.Event()
            current_task = asyncio.current_task()
            waiter = asyncio.create_task(stop_event.wait())
            waiter.add_done_callback(lambda _: current_task.cancel() if current_task else None)
            try:
                self.stop_event = stop_event
                yield stop_event
            finally:
                waiter.cancel()

    class _DummyManager:
        def __init__(self) -> None:
            self.runtime = _DummyRuntime()
            self.calls: list[str] = []

        async def run(self) -> None:
            self.calls.append("start")
            try:
                await asyncio.Event().wait()
            finally:
                self.calls.append("stop")

    manager = _DummyManager()
    task = asyncio.create_task(_serve_channels(manager))
    await asyncio.sleep(0.05)
    assert manager.calls == ["start"]
    manager.runtime.stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert manager.calls == ["start", "stop"]
