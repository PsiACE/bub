import asyncio

import pytest

from bub.channels.base import BaseChannel
from bub.channels.bus import MessageBus
from bub.channels.events import InboundMessage, OutboundMessage
from bub.channels.manager import ChannelManager
from bub.core.agent_loop import LoopResult


class FakeRuntime:
    async def handle_input(self, _session_id: str, _text: str) -> LoopResult:
        return LoopResult(
            immediate_output="",
            assistant_output="hello from loop",
            exit_requested=False,
            steps=1,
            error=None,
        )


class FakeChannel(BaseChannel):
    name = "fake"

    def __init__(self, bus: MessageBus) -> None:
        super().__init__(bus)
        self.sent: list[str] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message.content)


@pytest.mark.asyncio
async def test_channel_manager_routes_inbound_to_outbound() -> None:
    bus = MessageBus()
    manager = ChannelManager(bus, FakeRuntime())  # type: ignore[arg-type]
    channel = FakeChannel(bus)
    manager.register(channel)
    await manager.start()
    try:
        await bus.publish_inbound(
            InboundMessage(
                channel="fake",
                sender_id="u1",
                chat_id="c1",
                content="hello",
            )
        )
        await asyncio.sleep(0.05)
        assert channel.sent == ["hello from loop"]
    finally:
        await manager.stop()
