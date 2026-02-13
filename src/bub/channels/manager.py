"""Channel manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

from loguru import logger

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
        self._unsub_inbound: Callable[[], None] | None = None
        self._unsub_outbound: Callable[[], None] | None = None

    def register(self, channel: BaseChannel) -> None:
        self._channels[channel.name] = channel

    @property
    def channels(self) -> dict[str, BaseChannel]:
        return dict(self._channels)

    async def start(self) -> None:
        self._unsub_inbound = self.bus.on_inbound(self._process_inbound)
        self._unsub_outbound = self.bus.on_outbound(self._process_outbound)
        logger.info("channel.manager.start channels={}", sorted(self._channels.keys()))
        for channel in self._channels.values():
            await channel.start()

    async def stop(self) -> None:
        logger.info("channel.manager.stop")
        for channel in self._channels.values():
            await channel.stop()
        if self._unsub_inbound is not None:
            self._unsub_inbound()
            self._unsub_inbound = None
        if self._unsub_outbound is not None:
            self._unsub_outbound()
            self._unsub_outbound = None

    async def _process_inbound(self, message: InboundMessage) -> None:
        try:
            result = await self.runtime.handle_input(message.session_id, message.render())
            parts = [part for part in (result.immediate_output, result.assistant_output) if part]
            if result.error:
                parts.append(f"error: {result.error}")
            output = "\n\n".join(parts).strip()
            if not output:
                return

            # Extract message_id for reply functionality in group chats
            reply_to_message_id = message.metadata.get("message_id")

            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=message.channel,
                    chat_id=message.chat_id,
                    content=output,
                    metadata={"session_id": message.session_id},
                    reply_to_message_id=reply_to_message_id,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "channel.inbound.error channel={} chat_id={} session_id={}",
                message.channel,
                message.chat_id,
                message.session_id,
            )

    async def _process_outbound(self, message: OutboundMessage) -> None:
        try:
            channel = self._channels.get(message.channel)
            if channel is None:
                return
            await channel.send(message)
        except Exception:
            logger.exception(
                "channel.outbound.error channel={} chat_id={}",
                message.channel,
                message.chat_id,
            )

    def enabled_channels(self) -> Iterable[str]:
        return self._channels.keys()
