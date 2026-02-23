import asyncio
from typing import Any

from loguru import logger

from bub.channels.base import BaseChannel


class SessionRunner:
    def __init__(
        self, channel: BaseChannel, session_id: str, debounce_seconds: int, message_delay_seconds: int
    ) -> None:
        self.session_id = session_id
        self.channel = channel
        self.debounce_seconds = debounce_seconds
        self.message_delay_seconds = message_delay_seconds
        self._prompts: list[str] = []
        self._event = asyncio.Event()
        self._timer: asyncio.TimerHandle | None = None
        self._last_received_at: float | None = None
        self._running_task: asyncio.Task[None] | None = None
        self._loop = asyncio.get_running_loop()

    async def _run(self) -> None:
        await self._event.wait()
        prompt = f"channel: ${self.channel.output_channel}\n" + "\n".join(self._prompts)
        self._prompts.clear()
        self._running_task = None
        if (
            self._last_received_at is not None
            and self._loop.time() - self._last_received_at > self.message_delay_seconds
        ):
            self._last_received_at = None
        try:
            result = await self.channel.run_prompt(self.session_id, prompt)
            await self.channel.process_output(self.session_id, result)
        except Exception:
            logger.exception("session.run.error session_id={}", self.session_id)

    def reset_timer(self, timeout: int) -> None:
        self._event.clear()
        if self._timer:
            self._timer.cancel()
        self._timer = self._loop.call_later(timeout, self._event.set)

    async def process_message(self, message: Any) -> None:
        is_mentioned = self.channel.is_mentioned(message)
        _, prompt = await self.channel.get_session_prompt(message)
        now = self._loop.time()
        if not is_mentioned and self._last_received_at is None:
            return
        self._prompts.append(prompt)
        if prompt.startswith(","):
            logger.info("session.receive.command session_id={} message={}", self.session_id, prompt)
            try:
                result = await self.channel.run_prompt(self.session_id, prompt)
                await self.channel.process_output(self.session_id, result)
            except Exception:
                logger.exception("session.run.error session_id={}", self.session_id)
        elif is_mentioned:
            # wait at most 1 second to reply to mentioned messages.
            self._last_received_at = now
            logger.info("session.receive.mentioned session_id={} message={}", self.session_id, prompt)
            self.reset_timer(self.debounce_seconds)
            if self._running_task is None:
                self._running_task = asyncio.create_task(self._run())
            return await self._running_task
        elif self._last_received_at is not None and self._running_task is None:
            # Otherwise if bot is mentioned before, we will keep reading messages for at most 30 seconds.
            logger.info("session.receive followup session_id={} message={}", self.session_id, prompt)
            self.reset_timer(self.message_delay_seconds)
            self._running_task = asyncio.create_task(self._run())
            return await self._running_task
        else:
            logger.info("session.receive ignored session_id={} message={}", self.session_id, prompt)
