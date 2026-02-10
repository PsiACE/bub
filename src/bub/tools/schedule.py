from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bub.app.runtime import AppRuntime

runtime: AppRuntime | None = None


def set_runtime(app_runtime: AppRuntime) -> None:
    global runtime
    runtime = app_runtime


def run_scheduled_reminder(message: str, session_id: str) -> None:
    from bub.channels.events import InboundMessage

    if runtime is None:
        logger.error("cannot send scheduled reminder: runtime is not set")
        return

    bus = runtime.bus
    if bus is None:
        logger.warning("cannot send scheduled reminder: runtime bus is not set")
        return

    channel, chat_id = session_id.split(":", 1)
    inbound_message = InboundMessage(
        channel=channel,
        sender_id="scheduler",
        chat_id=chat_id,
        content=message,
    )
    logger.info("sending scheduled reminder to channel={} chat_id={} message={}", channel, chat_id, message)

    if runtime.loop is not None and runtime.loop.is_running():
        runtime.loop.call_soon_threadsafe(lambda: asyncio.create_task(bus.publish_inbound(inbound_message)))
        return

    asyncio.run(bus.publish_inbound(inbound_message))
