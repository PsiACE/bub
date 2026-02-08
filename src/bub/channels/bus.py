"""Signal-based channel bus."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from blinker import Signal

from bub.channels.events import InboundMessage, OutboundMessage

InboundHandler = Callable[[InboundMessage], None]
OutboundHandler = Callable[[OutboundMessage], None]


class MessageBus:
    """In-process message bus backed by blinker signals."""

    def __init__(self) -> None:
        self._inbound = Signal("bub.inbound")
        self._outbound = Signal("bub.outbound")

    def publish_inbound(self, message: InboundMessage) -> None:
        self._inbound.send(self, message=message)

    def publish_outbound(self, message: OutboundMessage) -> None:
        self._outbound.send(self, message=message)

    def on_inbound(self, handler: InboundHandler) -> Callable[[], None]:
        def _receiver(sender: Any, *, message: InboundMessage) -> None:
            handler(message)

        self._inbound.connect(_receiver, weak=False)
        return lambda: self._inbound.disconnect(_receiver)

    def on_outbound(self, handler: OutboundHandler) -> Callable[[], None]:
        def _receiver(sender: Any, *, message: OutboundMessage) -> None:
            handler(message)

        self._outbound.connect(_receiver, weak=False)
        return lambda: self._outbound.disconnect(_receiver)
