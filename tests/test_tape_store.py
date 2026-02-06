"""Tests for tape store persistence and concurrency behavior."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from republic.tape.entries import TapeEntry

from bub.tape.store import FileTapeStore


def _append_batch(
    store: FileTapeStore,
    *,
    batch_id: int,
    count: int,
    start_barrier: threading.Barrier,
) -> None:
    start_barrier.wait()
    for offset in range(count):
        payload = {"role": "user", "content": f"{batch_id}:{offset}"}
        store.append("bub", TapeEntry(0, "message", payload, {}))


def test_file_tape_store_assigns_unique_ids_under_concurrency(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BUB_HOME", str(tmp_path / "bubhome"))
    store = FileTapeStore(tmp_path)

    workers = 8
    per_worker = 40
    barrier = threading.Barrier(workers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for batch_id in range(workers):
            pool.submit(
                _append_batch,
                store,
                batch_id=batch_id,
                count=per_worker,
                start_barrier=barrier,
            )

    entries = store.read("bub")
    assert entries is not None

    ids = [entry.id for entry in entries]
    assert len(ids) == workers * per_worker
    assert len(set(ids)) == len(ids)
    assert sorted(ids) == list(range(1, len(ids) + 1))
