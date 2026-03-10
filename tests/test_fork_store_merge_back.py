from __future__ import annotations

import pytest
from republic import TapeEntry
from republic.tape import InMemoryTapeStore

from bub.builtin.store import ForkTapeStore


@pytest.mark.asyncio
async def test_fork_merge_back_true_merges_entries() -> None:
    """With merge_back=True (default), forked entries are merged into the parent."""
    parent = InMemoryTapeStore()
    store = ForkTapeStore(parent)

    async with store.fork("test-tape", merge_back=True):
        await store.append("test-tape", TapeEntry.event(name="step", data={"x": 1}))
        await store.append("test-tape", TapeEntry.event(name="step", data={"x": 2}))

    entries = parent.read("test-tape")
    assert entries is not None
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_fork_merge_back_false_discards_entries() -> None:
    """With merge_back=False, forked entries are NOT merged into the parent."""
    parent = InMemoryTapeStore()
    store = ForkTapeStore(parent)

    async with store.fork("test-tape", merge_back=False):
        await store.append("test-tape", TapeEntry.event(name="step", data={"x": 1}))

    entries = parent.read("test-tape")
    # No entries should have been merged
    assert entries is None or len(entries) == 0


@pytest.mark.asyncio
async def test_fork_default_merge_back_is_true() -> None:
    """The default value of merge_back should be True."""
    parent = InMemoryTapeStore()
    store = ForkTapeStore(parent)

    async with store.fork("test-tape"):
        await store.append("test-tape", TapeEntry.event(name="step", data={"v": 1}))

    entries = parent.read("test-tape")
    assert entries is not None
    assert len(entries) == 1
