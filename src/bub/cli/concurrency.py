from __future__ import annotations

import asyncio
from collections.abc import Awaitable


async def wait_until_stopped[T](coro: Awaitable[T], stop_event: asyncio.Event) -> T:
    """Wait for the given coroutine to complete, unless the stop_event is set first."""
    fut = asyncio.ensure_future(coro)
    waiter = asyncio.ensure_future(stop_event.wait())
    waiter.add_done_callback(lambda _: fut.cancel())
    try:
        return await fut
    finally:
        waiter.cancel()
