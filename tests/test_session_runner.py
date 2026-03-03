from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from bub.channels.base import BaseChannel
from bub.channels.runner import SessionRunner
from bub.core.agent_loop import LoopResult


class _Runtime:
    pass


class _ImmediateChannel(BaseChannel[str]):
    name = "cli"

    def __init__(self) -> None:
        super().__init__(_Runtime())  # type: ignore[arg-type]
        self.run_prompts: list[str] = []
        self.processed = 0

    @property
    def debounce_enabled(self) -> bool:
        return False

    async def start(self, on_receive: Callable[[str], Awaitable[None]]) -> None:
        _ = on_receive

    def is_mentioned(self, message: str) -> bool:
        _ = message
        return True

    async def get_session_prompt(self, message: str) -> tuple[str, str]:
        return "cli:test", message

    async def run_prompt(self, session_id: str, prompt: str) -> LoopResult:
        _ = session_id
        self.run_prompts.append(prompt)
        return LoopResult(
            immediate_output="",
            assistant_output="",
            exit_requested=False,
            steps=0,
            error=None,
        )

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        _ = (session_id, output)
        self.processed += 1


class _DebouncedChannel(BaseChannel[str]):
    name = "telegram"

    def __init__(self) -> None:
        super().__init__(_Runtime())  # type: ignore[arg-type]
        self.run_prompts: list[str] = []

    async def start(self, on_receive: Callable[[str], Awaitable[None]]) -> None:
        _ = on_receive

    def is_mentioned(self, message: str) -> bool:
        _ = message
        return True

    async def get_session_prompt(self, message: str) -> tuple[str, str]:
        return "telegram:1", message

    async def run_prompt(self, session_id: str, prompt: str) -> LoopResult:
        _ = session_id
        self.run_prompts.append(prompt)
        return LoopResult(
            immediate_output="",
            assistant_output="",
            exit_requested=False,
            steps=0,
            error=None,
        )

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        _ = (session_id, output)


class _ImmediateFailingChannel(_ImmediateChannel):
    async def run_prompt(self, session_id: str, prompt: str) -> LoopResult:
        _ = (session_id, prompt)
        raise RuntimeError("cli failure")


@pytest.mark.asyncio
async def test_session_runner_runs_non_debounced_channel_immediately() -> None:
    runner = SessionRunner(
        session_id="cli:test",
        debounce_seconds=10,
        message_delay_seconds=10,
        active_time_window_seconds=60,
    )
    channel = _ImmediateChannel()

    await runner.process_message(channel, "first")
    await runner.process_message(channel, "second")

    assert channel.run_prompts == ["first", "second"]
    assert channel.processed == 2


@pytest.mark.asyncio
async def test_command_prompt_is_not_buffered() -> None:
    runner = SessionRunner(
        session_id="telegram:1",
        debounce_seconds=1,
        message_delay_seconds=1,
        active_time_window_seconds=60,
    )
    channel = _DebouncedChannel()

    await runner.process_message(channel, ",help")

    assert channel.run_prompts == [",help"]
    assert runner._prompts == []
    assert runner._running_task is None


@pytest.mark.asyncio
async def test_session_runner_does_not_leak_command_into_batched_prompt() -> None:
    runner = SessionRunner(
        session_id="telegram:1",
        debounce_seconds=0,
        message_delay_seconds=0,
        active_time_window_seconds=60,
    )
    channel = _DebouncedChannel()

    await runner.process_message(channel, ",help")
    await runner.process_message(channel, "hello")

    assert channel.run_prompts[0] == ",help"
    assert channel.run_prompts[1] == "channel: $telegram\nhello"


@pytest.mark.asyncio
async def test_session_runner_raises_for_non_debounced_channel_errors() -> None:
    runner = SessionRunner(
        session_id="cli:test",
        debounce_seconds=10,
        message_delay_seconds=10,
        active_time_window_seconds=60,
    )
    channel = _ImmediateFailingChannel()

    with pytest.raises(RuntimeError, match="cli failure"):
        await runner.process_message(channel, "hello")
