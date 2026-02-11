from __future__ import annotations

import asyncio

from loguru import logger


def run_scheduled_reminder(message: str, session_id: str, runtime_id: str | None = None) -> None:
    from bub.app import get_runtime
    from bub.channels.events import InboundMessage

    runtime = get_runtime(runtime_id)

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
