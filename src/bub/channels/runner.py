import asyncio
import re
from typing import Any

from loguru import logger

from bub.channels.base import BaseChannel

DATA_URL_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+")
PROMPT_PREVIEW_LIMIT = 200


class SessionRunner:
    def __init__(
        self, session_id: str, debounce_seconds: int, message_delay_seconds: int, active_time_window_seconds: int
    ) -> None:
        self.session_id = session_id
        self.debounce_seconds = debounce_seconds
        self.message_delay_seconds = message_delay_seconds
        self.active_time_window_seconds = active_time_window_seconds
        self._prompts: list[str] = []
        self._event = asyncio.Event()
        self._timer: asyncio.TimerHandle | None = None
        self._last_mentioned_at: float | None = None
        self._running_task: asyncio.Task[None] | None = None
        self._loop = asyncio.get_running_loop()

    async def _run(self, channel: BaseChannel) -> None:
        await self._event.wait()
        prompt = channel.format_prompt("\n".join(self._prompts))
        self._prompts.clear()
        self._running_task = None
        try:
            result = await channel.run_prompt(self.session_id, prompt)
            await channel.process_output(self.session_id, result)
        except Exception:
            if not channel.debounce_enabled:
                raise
            logger.exception("session.run.error session_id={}", self.session_id)

    def reset_timer(self, timeout: int) -> None:
        self._event.clear()
        if self._timer:
            self._timer.cancel()
        self._timer = self._loop.call_later(timeout, self._event.set)

    @staticmethod
    def _preview_prompt(prompt: str) -> str:
        compact = DATA_URL_RE.sub("data:image/...;base64,<omitted>", prompt.replace("\n", "\\n"))
        if len(compact) <= PROMPT_PREVIEW_LIMIT:
            return compact
        return f"{compact[:PROMPT_PREVIEW_LIMIT]}..."

    async def process_message(self, channel: BaseChannel, message: Any) -> None:
        is_mentioned = channel.is_mentioned(message)
        _, prompt = await channel.get_session_prompt(message)
        prompt_preview = self._preview_prompt(prompt)
        now = self._loop.time()
        if not is_mentioned and (
            self._last_mentioned_at is None or now - self._last_mentioned_at > self.active_time_window_seconds
        ):
            self._last_mentioned_at = None
            logger.info("session.receive ignored session_id={} message={}", self.session_id, prompt_preview)
            return
        if prompt.startswith(","):
            logger.info("session.receive.command session_id={} message={}", self.session_id, prompt_preview)
            try:
                result = await channel.run_prompt(self.session_id, prompt)
                await channel.process_output(self.session_id, result)
            except Exception:
                if not channel.debounce_enabled:
                    raise
                logger.exception("session.run.error session_id={}", self.session_id)
            return
        elif not channel.debounce_enabled:
            logger.info("session.receive.immediate session_id={} message={}", self.session_id, prompt_preview)
            result = await channel.run_prompt(self.session_id, prompt)
            await channel.process_output(self.session_id, result)
            return

        self._prompts.append(prompt)
        if is_mentioned:
            # Debounce mentioned messages before responding.
            self._last_mentioned_at = now
            logger.info("session.receive.mentioned session_id={} message={}", self.session_id, prompt_preview)
            self.reset_timer(self.debounce_seconds)
            if self._running_task is None:
                self._running_task = asyncio.create_task(self._run(channel))
            return await self._running_task
        elif self._last_mentioned_at is not None and self._running_task is None:
            # Otherwise if bot is mentioned before, we will keep reading messages for at most 60s.
            logger.info("session.receive followup session_id={} message={}", self.session_id, prompt_preview)
            self.reset_timer(self.message_delay_seconds)
            self._running_task = asyncio.create_task(self._run(channel))
            return await self._running_task
