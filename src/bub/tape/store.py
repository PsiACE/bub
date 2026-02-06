"""Persistent tape store for Bub."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path

from republic.tape.entries import TapeEntry
from republic.tape.store import TapeStore

DEFAULT_TAPE_NAME = "bub"


@dataclass(frozen=True)
class TapePaths:
    """Resolved tape paths for a workspace."""

    home: Path
    tape_file: Path


def resolve_bub_home() -> Path:
    """Resolve the Bub home directory."""
    home = os.getenv("BUB_HOME")
    if home:
        return Path(home).expanduser()
    return Path.home() / ".bub"


def workspace_hash(path: Path) -> str:
    """Compute a stable hash for a workspace path."""
    resolved = path.resolve()
    return md5(str(resolved).encode("utf-8")).hexdigest()  # noqa: S324


def resolve_tape_paths(workspace_path: Path) -> TapePaths:
    """Resolve tape storage paths for a workspace."""
    home = resolve_bub_home()
    tape_dir = home / "tapes"
    tape_dir.mkdir(parents=True, exist_ok=True)
    tape_file = tape_dir / f"{workspace_hash(workspace_path)}.jsonl"
    return TapePaths(home=home, tape_file=tape_file)


class FileTapeStore(TapeStore):
    """Append-only JSONL tape store (single-tape per workspace)."""

    def __init__(self, workspace_path: Path, tape_name: str = DEFAULT_TAPE_NAME) -> None:
        self._tape_name = tape_name
        self._paths = resolve_tape_paths(workspace_path)
        self._next_id: int | None = None
        self._lock = threading.Lock()

    @property
    def tape_file(self) -> Path:
        return self._paths.tape_file

    def list_tapes(self) -> list[str]:
        if self.tape_file.exists():
            return [self._tape_name]
        return []

    def reset(self, _tape: str) -> None:
        with self._lock:
            if self.tape_file.exists():
                self.tape_file.unlink()
            self._next_id = None

    def read(self, _tape: str) -> list[TapeEntry] | None:
        with self._lock:
            if not self.tape_file.exists():
                return None
            entries: list[TapeEntry] = []
            try:
                with self.tape_file.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        entry = _entry_from_payload(payload)
                        if entry is not None:
                            entries.append(entry)
            except FileNotFoundError:
                return None
            return entries

    def append(self, _tape: str, entry: TapeEntry) -> None:
        with self._lock:
            next_id = self._next_entry_id()
            stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
            with self.tape_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_entry_to_payload(stored), ensure_ascii=False) + "\n")
            self._next_id = next_id + 1

    def archive(self) -> Path | None:
        with self._lock:
            if not self.tape_file.exists():
                return None
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            archive_path = self.tape_file.with_name(f"{self.tape_file.stem}.{timestamp}{self.tape_file.suffix}")
            self.tape_file.rename(archive_path)
            self._next_id = None
            return archive_path

    def _next_entry_id(self) -> int:
        if self._next_id is not None:
            return self._next_id
        self._next_id = _read_last_id(self.tape_file) + 1
        return self._next_id


def _read_last_id(path: Path) -> int:
    if not path.exists():
        return 0
    last_id = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                entry_id = payload.get("id")
                if isinstance(entry_id, int) and entry_id > last_id:
                    last_id = entry_id
    except FileNotFoundError:
        return 0
    return last_id


def _entry_from_payload(payload: dict) -> TapeEntry | None:
    entry_id = payload.get("id")
    kind = payload.get("kind")
    entry_payload = payload.get("payload")
    meta = payload.get("meta") or {}
    if not isinstance(entry_id, int):
        return None
    if not isinstance(kind, str):
        return None
    if not isinstance(entry_payload, dict):
        return None
    if not isinstance(meta, dict):
        meta = {}
    return TapeEntry(entry_id, kind, dict(entry_payload), dict(meta))


def _entry_to_payload(entry: TapeEntry) -> dict:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "payload": dict(entry.payload),
        "meta": dict(entry.meta),
    }
