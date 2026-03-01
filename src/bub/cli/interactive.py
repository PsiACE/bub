"""Backward-compatible interactive CLI wrapper."""

from __future__ import annotations

from bub.channels.cli import CliChannel


class InteractiveCli(CliChannel):
    """Compatibility wrapper that runs the CLI channel directly."""

    async def run(self) -> None:
        async with self.runtime.graceful_shutdown():
            await self.start(self._handle_local_input)

    async def _handle_local_input(self, message: str) -> None:
        session_id, prompt = await self.get_session_prompt(message)
        result = await self.run_prompt(session_id, prompt)
        await self.process_output(session_id, result)
