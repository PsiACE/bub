"""Persistent tape store implementation."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import cast
from urllib.parse import quote, unquote

from republic.tape import InMemoryQueryMixin, TapeEntry

TAPE_FILE_SUFFIX = ".jsonl"


@dataclass(frozen=True)
class TapePaths:
    """Resolved tape paths for one workspace."""

    home: Path
    tape_root: Path
    workspace_hash: str


class TapeFile:
    """Helper for one tape file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fork_start_id: int | None = None
        self._lock = threading.Lock()
        self._read_entries: list[TapeEntry] = []
        self._read_offset = 0

    def copy_to(self, target: TapeFile) -> None:
        if self.path.exists():
            shutil.copy2(self.path, target.path)
        target._read_entries = self.read()
        target.fork_start_id = self._next_id()
        target._read_offset = self._read_offset

    def copy_from(self, source: TapeFile) -> None:
        entries = [entry for entry in source.read() if entry.id >= (source.fork_start_id or 0)]
        self._append_many(entries)
        # Refresh to update intenal state
        self.read()

    def _next_id(self) -> int:
        if self._read_entries:
            return cast(int, self._read_entries[-1].id + 1)
        return 1

    def _reset(self) -> None:
        self._read_entries = []
        self._read_offset = 0

    def reset(self) -> None:
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            self._reset()

    def read(self) -> list[TapeEntry]:
        with self._lock:
            return self._read_locked()

    def _read_locked(self) -> list[TapeEntry]:
        if not self.path.exists():
            self._reset()
            return []

        file_size = self.path.stat().st_size
        if file_size < self._read_offset:
            # The file was truncated or replaced, so cached entries are stale.
            self._reset()

        with self.path.open("r", encoding="utf-8") as handle:
            handle.seek(self._read_offset)
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry = self.entry_from_payload(payload)
                if entry is not None:
                    self._read_entries.append(entry)
            self._read_offset = handle.tell()

        return list(self._read_entries)

    @staticmethod
    def entry_to_payload(entry: TapeEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "kind": entry.kind,
            "payload": dict(entry.payload),
            "meta": dict(entry.meta),
            "timestamp": entry.timestamp,
        }

    @staticmethod
    def entry_from_payload(payload: object) -> TapeEntry | None:
        if not isinstance(payload, dict):
            return None
        entry_id = payload.get("id")
        kind = payload.get("kind")
        entry_payload = payload.get("payload")
        meta = payload.get("meta")
        if not isinstance(entry_id, int):
            return None
        if not isinstance(kind, str):
            return None
        if not isinstance(entry_payload, dict):
            return None
        if not isinstance(meta, dict):
            meta = {}
        timestamp = payload.get("timestamp", 0.0)
        return TapeEntry(entry_id, kind, dict(entry_payload), dict(meta), timestamp)

    def append(self, entry: TapeEntry) -> None:
        return self._append_many([entry])

    def _append_many(self, entries: list[TapeEntry]) -> None:
        if not entries:
            return

        with self._lock:
            # Keep cache and offset in sync before allocating new IDs.
            self._read_locked()
            with self.path.open("a", encoding="utf-8") as handle:
                next_id = self._next_id()
                for entry in entries:
                    stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
                    handle.write(json.dumps(self.entry_to_payload(stored), ensure_ascii=False) + "\n")
                    self._read_entries.append(stored)
                    next_id += 1
                self._read_offset = handle.tell()

    def archive(self) -> Path | None:
        if not self.path.exists():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive_file = self.path.with_suffix(f"{TAPE_FILE_SUFFIX}.{stamp}.bak")
        self.path.replace(archive_file)
        return archive_file


class FileTapeStore(InMemoryQueryMixin):
    """Append-only JSONL tape store compatible with Republic TapeStore protocol."""

    def __init__(self, home: Path, workspace_path: Path) -> None:
        self._paths = self._resolve_paths(home, workspace_path)
        self._tape_files: dict[str, TapeFile] = {}
        self._fork_start_ids: dict[str, int] = {}
        self._lock = threading.Lock()

    def list_tapes(self) -> list[str]:
        with self._lock:
            tapes: list[str] = []
            prefix = f"{self._paths.workspace_hash}__"
            for path in self._paths.tape_root.glob(f"{prefix}*{TAPE_FILE_SUFFIX}"):
                encoded = path.name.removeprefix(prefix).removesuffix(TAPE_FILE_SUFFIX)
                if not encoded or "__" in encoded:
                    continue
                tapes.append(unquote(encoded))
            return sorted(set(tapes))

    def fork(self, source: str) -> str:
        fork_suffix = uuid.uuid4().hex[:8]
        new_name = f"{source}__{fork_suffix}"
        source_file = self._tape_file(source)
        target_file = self._tape_file(new_name)
        source_file.copy_to(target_file)
        return new_name

    def merge(self, source: str, target: str) -> None:
        source_file = self._tape_file(source)
        target_file = self._tape_file(target)
        target_file.copy_from(source_file)
        source_file.path.unlink(missing_ok=True)
        self._tape_files.pop(source, None)

    def reset(self, tape: str) -> None:
        return self._tape_file(tape).reset()

    def read(self, tape: str) -> list[TapeEntry] | None:
        tape_file = self._tape_file(tape)
        if not tape_file.path.exists():
            return None
        return tape_file.read()

    def append(self, tape: str, entry: TapeEntry) -> None:
        return self._tape_file(tape).append(entry)

    def archive(self, tape: str) -> Path | None:
        tape_file = self._tape_file(tape)
        self._tape_files.pop(tape, None)
        return tape_file.archive()

    def _tape_file(self, tape: str) -> TapeFile:
        if tape not in self._tape_files:
            encoded_name = quote(tape, safe="")
            file_name = f"{self._paths.workspace_hash}__{encoded_name}{TAPE_FILE_SUFFIX}"
            self._tape_files[tape] = TapeFile(self._paths.tape_root / file_name)
        return self._tape_files[tape]

    @staticmethod
    def _resolve_paths(home: Path, workspace_path: Path) -> TapePaths:
        tape_root = (home / "tapes").resolve()
        tape_root.mkdir(parents=True, exist_ok=True)
        workspace_hash = md5(str(workspace_path.resolve()).encode("utf-8")).hexdigest()  # noqa: S324
        return TapePaths(home=home, tape_root=tape_root, workspace_hash=workspace_hash)
