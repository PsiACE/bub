import asyncio

import pytest

from bub.app.runtime import AppRuntime, _running_loop


def test_running_loop_returns_none_without_active_loop() -> None:
    assert _running_loop() is None


@pytest.mark.asyncio
async def test_running_loop_returns_current_running_loop() -> None:
    assert _running_loop() is asyncio.get_running_loop()


def test_handle_input_syncs_runtime_loop_to_active_loop() -> None:
    runtime = object.__new__(AppRuntime)
    runtime.loop = None
    runtime._active_inputs = set()

    class _DummySession:
        async def handle_input(self, text: str) -> str:
            assert runtime.loop is asyncio.get_running_loop()
            return text

    session = _DummySession()

    def _get_session(_session_id: str) -> _DummySession:
        return session

    runtime.get_session = _get_session

    result = asyncio.run(AppRuntime.handle_input(runtime, "cli", "ping"))
    assert result == "ping"
    assert runtime.loop is not None


def test_reset_session_context_ignores_missing_session() -> None:
    runtime = object.__new__(AppRuntime)
    runtime._sessions = {}
    AppRuntime.reset_session_context(runtime, "missing")


def test_reset_session_context_resets_existing_session() -> None:
    runtime = object.__new__(AppRuntime)

    class _DummySession:
        def __init__(self) -> None:
            self.calls = 0

        def reset_context(self) -> None:
            self.calls += 1

    session = _DummySession()
    runtime._sessions = {"telegram:1": session}
    AppRuntime.reset_session_context(runtime, "telegram:1")
    assert session.calls == 1


@pytest.mark.asyncio
async def test_cancel_active_inputs_cancels_running_tasks() -> None:
    runtime = object.__new__(AppRuntime)
    gate = asyncio.Event()
    cancelled = {"value": False}

    async def _pending() -> str:
        try:
            await gate.wait()
        finally:
            cancelled["value"] = True

    task = asyncio.create_task(_pending())
    runtime._active_inputs = {task}
    await asyncio.sleep(0)

    count = AppRuntime.cancel_active_inputs(runtime)
    assert count == 1

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled["value"] is True
