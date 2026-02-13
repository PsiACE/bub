"""Minimal async message bus used by Bub framework."""

from __future__ import annotations

import asyncio
from typing import Protocol

from bub.types import Envelope


class BusProtocol(Protocol):
    """Minimal async contract for Bub bus providers."""

    async def publish_inbound(self, message: Envelope) -> None: ...

    async def publish_outbound(self, message: Envelope) -> None: ...

    async def next_inbound(self, timeout_seconds: float | None = None) -> Envelope | None: ...

    async def next_outbound(self, timeout_seconds: float | None = None) -> Envelope | None: ...


class MessageBus:
    """In-memory async bus for inbound/outbound envelopes."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[Envelope] = asyncio.Queue()
        self._outbound: asyncio.Queue[Envelope] = asyncio.Queue()

    async def publish_inbound(self, message: Envelope) -> None:
        await self._inbound.put(message)

    async def publish_outbound(self, message: Envelope) -> None:
        await self._outbound.put(message)

    async def next_inbound(self, timeout_seconds: float | None = None) -> Envelope | None:
        if timeout_seconds is None:
            return await self._inbound.get()
        try:
            return await asyncio.wait_for(self._inbound.get(), timeout=timeout_seconds)
        except TimeoutError:
            return None

    async def next_outbound(self, timeout_seconds: float | None = None) -> Envelope | None:
        if timeout_seconds is None:
            return await self._outbound.get()
        try:
            return await asyncio.wait_for(self._outbound.get(), timeout=timeout_seconds)
        except TimeoutError:
            return None
