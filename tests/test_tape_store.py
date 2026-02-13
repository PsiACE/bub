from pathlib import Path

from republic import TapeEntry

from bub.tape.store import FileTapeStore, TapeFile


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


def test_tape_file_read_is_incremental(tmp_path: Path) -> None:
    tape_path = tmp_path / "tape.jsonl"
    tape_file = TapeFile(tape_path)

    tape_path.write_text(
        '{"id":1,"kind":"message","payload":{"content":"one"},"meta":{}}\n',
        encoding="utf-8",
    )
    first = tape_file.read()
    assert [entry.id for entry in first] == [1]

    with tape_path.open("a", encoding="utf-8") as handle:
        handle.write('{"id":2,"kind":"message","payload":{"content":"two"},"meta":{}}\n')
    second = tape_file.read()
    assert [entry.id for entry in second] == [1, 2]


def test_tape_file_read_handles_truncated_file(tmp_path: Path) -> None:
    tape_path = tmp_path / "tape.jsonl"
    tape_file = TapeFile(tape_path)

    tape_path.write_text(
        '{"id":1,"kind":"message","payload":{"content":"one"},"meta":{}}\n',
        encoding="utf-8",
    )
    assert [entry.id for entry in tape_file.read()] == [1]

    tape_path.write_text("", encoding="utf-8")
    assert tape_file.read() == []

    with tape_path.open("a", encoding="utf-8") as handle:
        handle.write('{"id":1,"kind":"message","payload":{"content":"reset"},"meta":{}}\n')
    after_truncate = tape_file.read()
    assert [entry.payload["content"] for entry in after_truncate] == ["reset"]
