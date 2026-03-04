import asyncio

import pytest

from bub.channels.utils import exclude_none, wait_until_stopped


def test_exclude_none_keeps_non_none_values() -> None:
    payload = {"a": 1, "b": None, "c": "x", "d": False}
    assert exclude_none(payload) == {"a": 1, "c": "x", "d": False}


@pytest.mark.asyncio
async def test_wait_until_stopped_returns_result_when_coroutine_finishes_first() -> None:
    stop_event = asyncio.Event()
    result = await wait_until_stopped(asyncio.sleep(0.01, result="done"), stop_event)
    assert result == "done"


@pytest.mark.asyncio
async def test_wait_until_stopped_cancels_when_stop_event_set() -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    with pytest.raises(asyncio.CancelledError):
        await wait_until_stopped(asyncio.sleep(0.2, result="done"), stop_event)
