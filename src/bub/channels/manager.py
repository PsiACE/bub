import asyncio
import contextlib
from collections.abc import Collection

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bub.channels.base import Channel
from bub.channels.handler import BufferedMessageHandler
from bub.channels.message import ChannelMessage
from bub.envelope import content_of, field_of
from bub.framework import BubFramework
from bub.types import Envelope, MessageHandler


class ChannelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUB_", extra="ignore", env_file=".env")

    enabled_channels: str = Field(
        default="all", description="Comma-separated list of enabled channels, or 'all' for all channels."
    )
    debounce_seconds: float = Field(
        default=1.0,
        description="Minimum seconds between processing two messages from the same channel to prevent overload.",
    )
    max_wait_seconds: float = Field(
        default=10.0,
        description="Maximum seconds to wait for processing before new messages reach the channel.",
    )
    active_time_window: float = Field(
        default=60.0,
        description="Time window in seconds to consider a channel active for processing messages.",
    )


class ChannelManager:
    def __init__(self, framework: BubFramework, enabled_channels: Collection[str] | None = None) -> None:
        self.framework = framework
        self._channels: dict[str, Channel] = {}
        self._settings = ChannelSettings()
        if enabled_channels is not None:
            self._enabled_channels = list(enabled_channels)
        else:
            self._enabled_channels = self._settings.enabled_channels.split(",")
        self._messages = asyncio.Queue[ChannelMessage]()
        self._ongoing_tasks: set[asyncio.Task] = set()
        self._session_handlers: dict[str, MessageHandler] = {}

    async def on_receive(self, message: ChannelMessage) -> None:
        channel = message.channel
        session_id = message.session_id
        if channel not in self._channels:
            logger.warning(f"Received message from unknown channel '{channel}', ignoring.")
            return
        if session_id not in self._session_handlers:
            handler: MessageHandler
            if self._channels[channel].needs_debounce:
                handler = BufferedMessageHandler(
                    self._messages.put,
                    active_time_window=self._settings.active_time_window,
                    max_wait_seconds=self._settings.max_wait_seconds,
                    debounce_seconds=self._settings.debounce_seconds,
                )
            else:
                handler = self._messages.put
            self._session_handlers[session_id] = handler
        await self._session_handlers[session_id](message)

    async def dispatch(self, message: Envelope) -> bool:
        channel_name = field_of(message, "channel")
        if channel_name is None:
            return False

        channel_key = str(channel_name)
        channel = self._channels.get(channel_key)
        if channel is None:
            logger.warning(f"channel.manager outbound ignored unknown channel '{channel_key}'.")
            return False

        outbound = ChannelMessage(
            session_id=str(field_of(message, "session_id", f"{channel_key}:default")),
            channel=channel_key,
            chat_id=str(field_of(message, "chat_id", "default")),
            content=content_of(message),
        )
        await channel.send(outbound)
        return True

    def enabled_channels(self) -> list[Channel]:
        if "all" in self._enabled_channels:
            return list(self._channels.values())
        return [channel for name, channel in self._channels.items() if name in self._enabled_channels]

    def _load_channels(self) -> None:
        for result in reversed(
            self.framework._hook_runtime.call_many_sync("provide_channels", message_handler=self.on_receive)
        ):
            for channel in result:
                self._channels[channel.name] = channel

    async def listen_and_run(self) -> None:
        self._load_channels()
        self.framework.bind_outbound_router(self)
        for channel in self.enabled_channels():
            await channel.start()
        logger.info("channel.manager started listening")
        try:
            while True:
                message = await self._messages.get()
                task = asyncio.create_task(self.framework.process_inbound(message))
                task.add_done_callback(lambda t: self._ongoing_tasks.discard(t))
                self._ongoing_tasks.add(task)
        except asyncio.CancelledError:
            logger.info("channel.manager received shutdown signal")
        except Exception:
            logger.exception("channel.manager error")
            raise
        finally:
            self.framework.bind_outbound_router(None)
            await self.shutdown()
            logger.info("channel.manager stopped")

    async def shutdown(self) -> None:
        count = 0
        while self._ongoing_tasks:
            task = self._ongoing_tasks.pop()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            count += 1
        logger.info(f"channel.manager cancelled {count} in-flight tasks")
        for channel in self.enabled_channels():
            await channel.stop()
