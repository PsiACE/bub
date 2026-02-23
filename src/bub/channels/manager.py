"""Channel manager."""

from __future__ import annotations

import asyncio
import contextlib
import functools

from loguru import logger

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel
from bub.channels.runner import SessionRunner


class ChannelManager:
    """Coordinate inbound routing and outbound dispatch for channels."""

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._channels: dict[str, BaseChannel] = {}
        self._channel_tasks: list[asyncio.Task[None]] = []
        self._session_runners: dict[str, SessionRunner] = {}
        for channel_cls in self.default_channels():
            self.register(channel_cls)
        runtime.install_hooks(self)

    def register[T: type[BaseChannel]](self, channel: T) -> T:
        self._channels[channel.name] = channel(self.runtime)
        return channel

    @property
    def channels(self) -> dict[str, BaseChannel]:
        return dict(self._channels)

    async def run(self) -> None:
        logger.info("channel.manager.start channels={}", self.enabled_channels())
        for channel in self._channels.values():
            task = asyncio.create_task(channel.start(functools.partial(self._process_input, channel)))
            self._channel_tasks.append(task)
        try:
            await asyncio.gather(*self._channel_tasks)
        finally:
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

    async def _process_input[T](self, channel: BaseChannel[T], message: T) -> None:
        session_id, _ = await channel.get_session_prompt(message)
        if session_id not in self._session_runners:
            self._session_runners[session_id] = SessionRunner(
                channel,
                session_id,
                self.runtime.settings.message_debounce_seconds,
                self.runtime.settings.message_delay_seconds,
            )
        await self._session_runners[session_id].process_message(message)
