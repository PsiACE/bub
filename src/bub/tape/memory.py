"""Tape-native memory zone.

Memory lives as a delimited region within the tape, bounded by
``memory/open`` and ``memory/seal`` anchors.  Each write creates a new
versioned pair so the tape stays append-only while the "current" memory
is always the pair with the highest version number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from bub.tape.service import TapeService

MEMORY_OPEN_ANCHOR = "memory/open"
MEMORY_SEAL_ANCHOR = "memory/seal"
MEMORY_LONG_TERM_EVENT = "memory.long_term"
MEMORY_DAILY_EVENT = "memory.daily"
DEFAULT_DAILY_RETENTION_DAYS = 30


@dataclass(frozen=True)
class DailyNote:
    """One day's memory notes."""

    date: str  # "YYYY-MM-DD"
    content: str


@dataclass
class MemorySnapshot:
    """Point-in-time snapshot of the memory zone."""

    version: int = 0
    long_term: str = ""
    dailies: list[DailyNote] = field(default_factory=list)

    def get_daily(self, date: str) -> str | None:
        """Return content for a specific date, or ``None``."""
        for daily in self.dailies:
            if daily.date == date:
                return daily.content
        return None

    def recent_dailies(self, days: int = 7) -> list[DailyNote]:
        """Return dailies from the last *days* days."""
        cutoff = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
        return [d for d in self.dailies if d.date >= cutoff]

    def set_daily(self, date: str, content: str) -> None:
        """Set (or replace) a daily note for *date*."""
        self.dailies = [d for d in self.dailies if d.date != date]
        self.dailies.append(DailyNote(date=date, content=content))
        self.dailies.sort(key=lambda d: d.date, reverse=True)

    def prune(self, retention_days: int = DEFAULT_DAILY_RETENTION_DAYS) -> int:
        """Drop dailies older than *retention_days*.  Returns count removed."""
        cutoff = (datetime.now(UTC).date() - timedelta(days=retention_days)).isoformat()
        before = len(self.dailies)
        self.dailies = [d for d in self.dailies if d.date >= cutoff]
        return before - len(self.dailies)


class MemoryZone:
    """Tape-native persistent memory.

    The zone is a pair of anchors (``memory/open`` … ``memory/seal``) that
    bracket ``memory.long_term`` and ``memory.daily`` event entries.  Every
    mutation appends a *new* versioned pair so the tape stays append-only.
    """

    def __init__(self, tape: TapeService, *, retention_days: int = DEFAULT_DAILY_RETENTION_DAYS) -> None:
        self._tape = tape
        self._retention_days = retention_days
        self._snapshot: MemorySnapshot | None = None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def ensure(self) -> None:
        """Ensure a memory zone exists on the tape; create an empty one if not."""
        snap = self._load_snapshot()
        if snap is not None:
            self._snapshot = snap
            return
        # No zone yet - write an empty v1
        self._snapshot = MemorySnapshot(version=1)
        self._write_zone(self._snapshot)
        logger.info("memory.zone.created version=1")

    def read(self) -> MemorySnapshot:
        """Return the latest memory snapshot (cached after first read)."""
        if self._snapshot is not None:
            return self._snapshot
        snap = self._load_snapshot()
        if snap is None:
            snap = MemorySnapshot()
        self._snapshot = snap
        return snap

    def get_context(self) -> str:
        """Format memory for system-prompt injection."""
        snap = self.read()
        parts: list[str] = []
        today = datetime.now(UTC).date().isoformat()

        if snap.long_term:
            parts.append("## Long-term Memory\n" + snap.long_term)

        # Today's notes get their own section
        today_content = snap.get_daily(today)
        if today_content:
            parts.append("## Today's Notes\n" + today_content)

        # Recent history (excluding today)
        recent = [d for d in snap.recent_dailies(days=7) if d.date != today]
        if recent:
            lines = ["## Recent Notes"]
            for daily in recent:
                lines.append(f"### {daily.date}")
                lines.append(daily.content)
            parts.append("\n".join(lines))

        if not parts:
            return ""

        # Add usage hint so the LLM knows how to interact with memory
        header = (
            "Use `memory.save` to update long-term memory, "
            "`memory.daily` to append to daily notes, "
            "and `memory.recall` to search past memories."
        )
        return header + "\n\n" + "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_long_term(self, content: str) -> None:
        """Replace the long-term memory content and rewrite the zone."""
        snap = self.read()
        snap.long_term = content
        self._bump_and_write(snap)
        logger.info("memory.long_term.saved version={}", snap.version)

    def append_daily(self, content: str, date: str | None = None) -> None:
        """Append content to today's (or a specific date's) daily note."""
        if date is None:
            date = datetime.now(UTC).date().isoformat()
        snap = self.read()
        existing = snap.get_daily(date)
        merged = existing + "\n" + content if existing else f"# {date}\n\n{content}"
        snap.set_daily(date, merged)
        self._bump_and_write(snap)
        logger.info("memory.daily.appended date={} version={}", date, snap.version)

    def clear(self) -> None:
        """Clear all memory (write an empty zone)."""
        snap = self.read()
        snap.long_term = ""
        snap.dailies = []
        self._bump_and_write(snap)
        logger.info("memory.cleared version={}", snap.version)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _bump_and_write(self, snap: MemorySnapshot) -> None:
        snap.version += 1
        self._write_zone(snap)
        self._snapshot = snap

    def prune(self) -> int:
        """Prune old daily notes.  Returns number removed."""
        snap = self.read()
        removed = snap.prune(retention_days=self._retention_days)
        if removed > 0:
            self._bump_and_write(snap)
            logger.info("memory.pruned removed={} version={}", removed, snap.version)
        return removed

    def _write_zone(self, snap: MemorySnapshot) -> None:
        """Append a new versioned memory zone to the tape."""
        self._tape.append_anchor(MEMORY_OPEN_ANCHOR, state={"version": snap.version})

        if snap.long_term:
            self._tape.append_event(
                MEMORY_LONG_TERM_EVENT,
                {
                    "content": snap.long_term,
                    "updated_at": _utc_now_iso(),
                },
            )

        for daily in snap.dailies:
            self._tape.append_event(
                MEMORY_DAILY_EVENT,
                {
                    "date": daily.date,
                    "content": daily.content,
                    "updated_at": _utc_now_iso(),
                },
            )

        self._tape.append_anchor(MEMORY_SEAL_ANCHOR, state={"version": snap.version})

    def _load_snapshot(self) -> MemorySnapshot | None:
        """Scan tape anchors and load the latest memory zone."""
        entries = self._tape.read_entries()
        seal_index, best_version = self._find_latest_seal(entries)
        if seal_index is None:
            return None
        open_index = self._find_matching_open(entries, seal_index, best_version)
        if open_index is None:
            return None
        return self._parse_zone_entries(entries[open_index + 1 : seal_index], best_version)

    @staticmethod
    def _find_latest_seal(entries: list[Any]) -> tuple[int | None, int]:
        """Return (index, version) of the highest-version memory/seal anchor."""
        best_version = 0
        seal_index: int | None = None
        for idx, entry in enumerate(entries):
            if entry.kind != "anchor":
                continue
            name = entry.payload.get("name")
            state = entry.payload.get("state")
            version = state.get("version") if isinstance(state, dict) else None
            if isinstance(version, int) and name == MEMORY_SEAL_ANCHOR and version > best_version:
                best_version = version
                seal_index = idx
        return seal_index, best_version

    @staticmethod
    def _find_matching_open(entries: list[Any], seal_index: int, version: int) -> int | None:
        """Walk backwards from *seal_index* to find the matching memory/open."""
        for idx in range(seal_index - 1, -1, -1):
            entry = entries[idx]
            if entry.kind != "anchor":
                continue
            name = entry.payload.get("name")
            state = entry.payload.get("state")
            entry_version = state.get("version") if isinstance(state, dict) else None
            if name == MEMORY_OPEN_ANCHOR and entry_version == version:
                return idx
        return None

    @staticmethod
    def _parse_zone_entries(entries: list[Any], version: int) -> MemorySnapshot:
        """Parse event entries between open and seal into a snapshot."""
        snap = MemorySnapshot(version=version)
        for entry in entries:
            if entry.kind != "event":
                continue
            event_name = entry.payload.get("name")
            data = entry.payload.get("data")
            if not isinstance(data, dict):
                continue
            if event_name == MEMORY_LONG_TERM_EVENT:
                content = data.get("content")
                if isinstance(content, str):
                    snap.long_term = content
            elif event_name == MEMORY_DAILY_EVENT:
                date_val = data.get("date")
                content = data.get("content")
                if isinstance(date_val, str) and isinstance(content, str):
                    snap.dailies.append(DailyNote(date=date_val, content=content))
        snap.dailies.sort(key=lambda d: d.date, reverse=True)
        return snap


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
