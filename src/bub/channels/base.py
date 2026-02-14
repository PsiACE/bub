"""Base channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from bub.app.runtime import AppRuntime

if TYPE_CHECKING:
    from bub.core import LoopResult


def exclude_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


class BaseChannel[T](ABC):
    """Abstract base class for channel adapters."""

    name: str = "base"

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    @abstractmethod
    async def start(self, on_receive: Callable[[T], Awaitable[None]]) -> None:
        """Start the channel and set up the receive callback."""

    @abstractmethod
    async def get_session_prompt(self, message: T) -> tuple[str, str]:
        """Get the session id and prompt text for the given message."""
        pass

    @abstractmethod
    async def process_output(self, session_id: str, output: LoopResult) -> None:
        """Process the output returned by the LLM."""
        pass

    async def run_prompt(self, message: T) -> None:
        """Run a prompt based on the received message."""
        try:
            session_id, prompt = await self.get_session_prompt(message)
            output = await self.runtime.handle_input(session_id, prompt)
            await self.process_output(session_id, output)
        except Exception:
            logger.exception("{}.agent.error", self.name)
