"""Base channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bub.channels.bus import MessageBus
from bub.channels.events import InboundMessage, OutboundMessage


class BaseChannel(ABC):
    """Abstract base class for channel adapters."""

    name = "base"

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start adapter and begin ingesting inbound messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop adapter and cleanup resources."""

    @abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        """Send one outbound message to external channel."""

    async def publish_inbound(self, message: InboundMessage) -> None:
        await self.bus.publish_inbound(message)

    @property
    def is_running(self) -> bool:
        return self._running
