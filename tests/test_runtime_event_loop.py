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
