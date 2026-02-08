"""Channel manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel
from bub.channels.bus import MessageBus
from bub.channels.events import InboundMessage, OutboundMessage


class ChannelManager:
    """Coordinate inbound routing and outbound dispatch for channels."""

    def __init__(self, bus: MessageBus, runtime: AppRuntime) -> None:
        self.bus = bus
        self.runtime = runtime
        self._channels: dict[str, BaseChannel] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._unsub_inbound: Callable[[], None] | None = None
        self._unsub_outbound: Callable[[], None] | None = None

    def register(self, channel: BaseChannel) -> None:
        self._channels[channel.name] = channel

    @property
    def channels(self) -> dict[str, BaseChannel]:
        return dict(self._channels)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._unsub_inbound = self.bus.on_inbound(self._handle_inbound)
        self._unsub_outbound = self.bus.on_outbound(self._handle_outbound)
        for channel in self._channels.values():
            self._tasks.append(asyncio.create_task(channel.start()))

    async def stop(self) -> None:
        for channel in self._channels.values():
            await channel.stop()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                continue
        self._tasks.clear()
        if self._unsub_inbound is not None:
            self._unsub_inbound()
            self._unsub_inbound = None
        if self._unsub_outbound is not None:
            self._unsub_outbound()
            self._unsub_outbound = None

    def _handle_inbound(self, message: InboundMessage) -> None:
        if self._loop is None:
            return
        self._loop.create_task(self._process_inbound(message))

    def _handle_outbound(self, message: OutboundMessage) -> None:
        if self._loop is None:
            return
        self._loop.create_task(self._process_outbound(message))

    async def _process_inbound(self, message: InboundMessage) -> None:
        result = self.runtime.handle_input(message.session_id, message.content)
        parts = [part for part in (result.immediate_output, result.assistant_output) if part]
        if result.error:
            parts.append(f"error: {result.error}")
        output = "\n\n".join(parts).strip()
        if not output:
            return
        self.bus.publish_outbound(
            OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content=output,
                metadata={"session_id": message.session_id},
            )
        )

    async def _process_outbound(self, message: OutboundMessage) -> None:
        channel = self._channels.get(message.channel)
        if channel is None:
            return
        await channel.send(message)

    def enabled_channels(self) -> Iterable[str]:
        return self._channels.keys()
