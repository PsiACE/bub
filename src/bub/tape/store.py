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
from urllib.parse import quote, unquote

from republic.tape import TapeEntry

TAPE_FILE_SUFFIX = ".jsonl"


@dataclass(frozen=True)
class TapePaths:
    """Resolved tape paths for one workspace."""

    home: Path
    tape_root: Path
    workspace_hash: str


class FileTapeStore:
    """Append-only JSONL tape store compatible with Republic TapeStore protocol."""

    def __init__(self, home: Path, workspace_path: Path) -> None:
        self._paths = self._resolve_paths(home, workspace_path)
        self._next_ids: dict[str, int] = {}
        self._fork_start_ids: dict[str, int] = {}
        self._lock = threading.Lock()

    def list_tapes(self) -> list[str]:
        with self._lock:
            tapes: list[str] = []
            prefix = f"{self._paths.workspace_hash}__"
            for path in self._paths.tape_root.glob(f"{prefix}*{TAPE_FILE_SUFFIX}"):
                encoded = path.name.removeprefix(prefix).removesuffix(TAPE_FILE_SUFFIX)
                if not encoded:
                    continue
                tapes.append(unquote(encoded))
            return sorted(set(tapes))

    def fork(self, source: str) -> str:
        with self._lock:
            fork_suffix = uuid.uuid4().hex[:8]
            new_name = f"{source}__{fork_suffix}"
            source_file = self._tape_file(source)
            target_file = self._tape_file(new_name)
            if source_file.exists():
                shutil.copy2(source_file, target_file)
            self._next_ids[new_name] = self._fork_start_ids[new_name] = self._next_entry_id(source, source_file)
            return new_name

    def merge(self, source: str, target: str) -> None:
        print("Merging", source, "into", target)
        all_entries = self.read(source) or []
        with self._lock:
            if source not in self._fork_start_ids:
                return
            source_file = self._tape_file(source)
            next_id = self._next_entry_id(source, source_file)
            fork_start_id = self._fork_start_ids[source]
            entries = [entry for entry in all_entries if fork_start_id <= entry.id < next_id]
            self._append_many(target, entries)
            del self._fork_start_ids[source]
            del self._next_ids[source]
            source_file.unlink(missing_ok=True)

    def reset(self, tape: str) -> None:
        with self._lock:
            tape_file = self._tape_file(tape)
            if tape_file.exists():
                tape_file.unlink()
            self._next_ids.pop(tape, None)

    def read(self, tape: str) -> list[TapeEntry] | None:
        with self._lock:
            tape_file = self._tape_file(tape)
            if not tape_file.exists():
                return None

            entries: list[TapeEntry] = []
            with tape_file.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    entry = self._entry_from_payload(payload)
                    if entry is not None:
                        entries.append(entry)
            return entries

    def append(self, tape: str, entry: TapeEntry) -> None:
        with self._lock:
            tape_file = self._tape_file(tape)
            next_id = self._next_entry_id(tape, tape_file)
            stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
            with tape_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self._entry_to_payload(stored), ensure_ascii=False) + "\n")
            self._next_ids[tape] = next_id + 1

    def _append_many(self, tape: str, entries: list[TapeEntry]) -> None:
        tape_file = self._tape_file(tape)
        next_id = self._next_entry_id(tape, tape_file)
        with tape_file.open("a", encoding="utf-8") as handle:
            for entry in entries:
                stored = TapeEntry(next_id, entry.kind, dict(entry.payload), dict(entry.meta))
                handle.write(json.dumps(self._entry_to_payload(stored), ensure_ascii=False) + "\n")
                next_id += 1
        self._next_ids[tape] = next_id

    def archive(self, tape: str) -> Path | None:
        with self._lock:
            tape_file = self._tape_file(tape)
            if not tape_file.exists():
                return None
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            archive_file = tape_file.with_suffix(f"{TAPE_FILE_SUFFIX}.{stamp}.bak")
            tape_file.replace(archive_file)
            self._next_ids.pop(tape, None)
            return archive_file

    def _next_entry_id(self, tape: str, tape_file: Path) -> int:
        if tape in self._next_ids:
            return self._next_ids[tape]

        last_id = 0
        if tape_file.exists():
            with tape_file.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    current_id = payload.get("id")
                    if isinstance(current_id, int) and current_id > last_id:
                        last_id = current_id

        self._next_ids[tape] = last_id + 1
        return self._next_ids[tape]

    def _tape_file(self, tape: str) -> Path:
        encoded_name = quote(tape, safe="")
        file_name = f"{self._paths.workspace_hash}__{encoded_name}{TAPE_FILE_SUFFIX}"
        return self._paths.tape_root / file_name

    @staticmethod
    def _entry_from_payload(payload: object) -> TapeEntry | None:
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
        return TapeEntry(entry_id, kind, dict(entry_payload), dict(meta))

    @staticmethod
    def _entry_to_payload(entry: TapeEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "kind": entry.kind,
            "payload": dict(entry.payload),
            "meta": dict(entry.meta),
        }

    @staticmethod
    def _resolve_paths(home: Path, workspace_path: Path) -> TapePaths:
        tape_root = (home / "tapes").resolve()
        tape_root.mkdir(parents=True, exist_ok=True)
        workspace_hash = md5(str(workspace_path.resolve()).encode("utf-8")).hexdigest()  # noqa: S324
        return TapePaths(home=home, tape_root=tape_root, workspace_hash=workspace_hash)
