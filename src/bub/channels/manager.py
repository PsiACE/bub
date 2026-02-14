"""Channel manager."""

from __future__ import annotations

import asyncio
import contextlib

from loguru import logger

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel


class ChannelManager:
    """Coordinate inbound routing and outbound dispatch for channels."""

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._channels: dict[str, BaseChannel] = {}
        self._channel_tasks: list[asyncio.Task[None]] = []
        for channel_cls in self.default_channels():
            self.register(channel_cls)

    def register[T: type[BaseChannel]](self, channel: T) -> T:
        self._channels[channel.name] = channel(self.runtime)
        return channel

    @property
    def channels(self) -> dict[str, BaseChannel]:
        return dict(self._channels)

    async def start(self) -> None:
        logger.info("channel.manager.start channels={}", self.enabled_channels())
        for channel in self._channels.values():
            # XXX: Currently we just call the same message handler with itself.
            # But it will be likely decoupled later
            task = asyncio.create_task(channel.start(channel.run_prompt))
            self._channel_tasks.append(task)

    async def stop(self) -> None:
        for task in self._channel_tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.gather(*self._channel_tasks)
        self._channel_tasks.clear()
        logger.info("channel.manager.stop")

    def enabled_channels(self) -> list[str]:
        return sorted(self._channels)

    def default_channels(self) -> list[type[BaseChannel]]:
        """Return the built-in channels."""

        result: list[type[BaseChannel]] = []

        if self.runtime.settings.telegram_enabled:
            from bub.channels.telegram import TelegramChannel

            result.append(TelegramChannel)
        if self.runtime.settings.discord_enabled:
            from bub.channels.discord import DiscordChannel

            result.append(DiscordChannel)
        return result
