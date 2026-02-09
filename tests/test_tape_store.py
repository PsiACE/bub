from pathlib import Path

from bub.tape.store import FileTapeStore
from republic import TapeEntry


def test_store_isolated_by_tape_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = FileTapeStore(home, workspace)

    store.append("a", TapeEntry.message({"role": "user", "content": "one"}))
    store.append("b", TapeEntry.message({"role": "user", "content": "two"}))

    a_entries = store.read("a")
    b_entries = store.read("b")
    assert a_entries is not None
    assert b_entries is not None
    assert a_entries[0].payload["content"] == "one"
    assert b_entries[0].payload["content"] == "two"
    assert sorted(store.list_tapes()) == ["a", "b"]


def test_archive_then_reset(tmp_path: Path) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = FileTapeStore(home, workspace)

    store.append("session", TapeEntry.event("command", {"raw": "echo hi"}))
    archive = store.archive("session")
    assert archive is not None
    assert archive.exists()
    assert store.read("session") is None
