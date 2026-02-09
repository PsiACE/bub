"""Signal-based channel bus."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from blinker import Signal

from bub.channels.events import InboundMessage, OutboundMessage

InboundHandler = Callable[[InboundMessage], Coroutine[Any, Any, None]]
OutboundHandler = Callable[[OutboundMessage], Coroutine[Any, Any, None]]


class MessageBus:
    """In-process message bus backed by blinker signals."""

    def __init__(self) -> None:
        self._inbound = Signal("bub.inbound")
        self._outbound = Signal("bub.outbound")

    async def publish_inbound(self, message: InboundMessage) -> None:
        await self._inbound.send_async(self, message=message)

    async def publish_outbound(self, message: OutboundMessage) -> None:
        await self._outbound.send_async(self, message=message)

    def on_inbound(self, handler: InboundHandler) -> Callable[[], None]:
        async def _receiver(sender: Any, *, message: InboundMessage) -> None:
            await handler(message)

        self._inbound.connect(_receiver, weak=False)
        return lambda: self._inbound.disconnect(_receiver)

    def on_outbound(self, handler: OutboundHandler) -> Callable[[], None]:
        async def _receiver(sender: Any, *, message: OutboundMessage) -> None:
            await handler(message)

        self._outbound.connect(_receiver, weak=False)
        return lambda: self._outbound.disconnect(_receiver)
