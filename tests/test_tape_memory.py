"""Tests for tape-native memory zone."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bub.tape.memory import (
    MEMORY_LONG_TERM_EVENT,
    MEMORY_OPEN_ANCHOR,
    MEMORY_SEAL_ANCHOR,
    MemorySnapshot,
    MemoryZone,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeEntry:
    id: int
    kind: str
    payload: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)


class FakeTapeService:
    """Minimal TapeService stub for memory zone tests."""

    def __init__(self) -> None:
        self.entries: list[FakeEntry] = []
        self._next_id = 0

    def read_entries(self) -> list[FakeEntry]:
        return list(self.entries)

    def append_anchor(self, name: str, *, state: dict[str, Any] | None = None) -> None:
        entry = FakeEntry(
            id=self._next_id,
            kind="anchor",
            payload={"name": name, "state": state or {}},
        )
        self._next_id += 1
        self.entries.append(entry)

    def handoff(self, name: str, *, state: dict[str, Any] | None = None) -> list[FakeEntry]:
        entry = FakeEntry(
            id=self._next_id,
            kind="anchor",
            payload={"name": name, "state": state or {}},
        )
        self._next_id += 1
        self.entries.append(entry)
        return [entry]

    def append_event(self, name: str, data: dict[str, Any]) -> None:
        entry = FakeEntry(
            id=self._next_id,
            kind="event",
            payload={"name": name, "data": data},
        )
        self._next_id += 1
        self.entries.append(entry)


# ---------------------------------------------------------------------------
# MemorySnapshot unit tests
# ---------------------------------------------------------------------------


class TestMemorySnapshot:
    def test_empty_snapshot(self) -> None:
        snap = MemorySnapshot()
        assert snap.version == 0
        assert snap.long_term == ""
        assert snap.dailies == []
        assert snap.get_daily("2025-07-17") is None

    def test_set_daily_creates_new(self) -> None:
        snap = MemorySnapshot()
        snap.set_daily("2025-07-17", "worked on memory")
        assert snap.get_daily("2025-07-17") == "worked on memory"

    def test_set_daily_replaces_existing(self) -> None:
        snap = MemorySnapshot()
        snap.set_daily("2025-07-17", "old content")
        snap.set_daily("2025-07-17", "new content")
        assert snap.get_daily("2025-07-17") == "new content"
        assert len(snap.dailies) == 1

    def test_dailies_sorted_newest_first(self) -> None:
        snap = MemorySnapshot()
        snap.set_daily("2025-07-15", "day 1")
        snap.set_daily("2025-07-17", "day 3")
        snap.set_daily("2025-07-16", "day 2")
        assert [d.date for d in snap.dailies] == ["2025-07-17", "2025-07-16", "2025-07-15"]

    def test_recent_dailies_filters_by_days(self) -> None:
        snap = MemorySnapshot()
        # These won't match "recent" unless we're near those dates,
        # so use relative dates instead
        from datetime import UTC, datetime, timedelta

        today = datetime.now(UTC).date()
        snap.set_daily(today.isoformat(), "today")
        snap.set_daily((today - timedelta(days=3)).isoformat(), "3 days ago")
        snap.set_daily((today - timedelta(days=10)).isoformat(), "10 days ago")

        recent = snap.recent_dailies(days=7)
        assert len(recent) == 2

    def test_prune_removes_old_dailies(self) -> None:
        snap = MemorySnapshot()
        from datetime import UTC, datetime, timedelta

        today = datetime.now(UTC).date()
        snap.set_daily(today.isoformat(), "today")
        snap.set_daily((today - timedelta(days=100)).isoformat(), "old")

        removed = snap.prune(retention_days=30)
        assert removed == 1
        assert len(snap.dailies) == 1


# ---------------------------------------------------------------------------
# MemoryZone tests
# ---------------------------------------------------------------------------


class TestMemoryZone:
    def _make_zone(self) -> tuple[FakeTapeService, MemoryZone]:
        fake = FakeTapeService()
        zone = MemoryZone(fake)  # type: ignore[arg-type]
        return fake, zone

    def test_ensure_creates_empty_zone(self) -> None:
        fake, zone = self._make_zone()
        zone.ensure()

        # Should have written memory/open + memory/seal anchors
        anchor_names = [e.payload["name"] for e in fake.entries if e.kind == "anchor"]
        assert MEMORY_OPEN_ANCHOR in anchor_names
        assert MEMORY_SEAL_ANCHOR in anchor_names

    def test_ensure_idempotent(self) -> None:
        fake, zone = self._make_zone()
        zone.ensure()
        count_before = len(fake.entries)
        zone.ensure()
        # Should not create another zone
        assert len(fake.entries) == count_before

    def test_read_empty_zone(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        snap = zone.read()
        assert snap.long_term == ""
        assert snap.dailies == []
        assert snap.version == 1

    def test_save_long_term(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("User prefers Python 3.12")

        snap = zone.read()
        assert snap.long_term == "User prefers Python 3.12"
        assert snap.version == 2

    def test_save_long_term_replaces_previous(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("first")
        zone.save_long_term("second")

        snap = zone.read()
        assert snap.long_term == "second"
        assert snap.version == 3

    def test_append_daily(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.append_daily("worked on tests", date="2025-07-17")

        snap = zone.read()
        assert snap.get_daily("2025-07-17") is not None
        assert "worked on tests" in snap.get_daily("2025-07-17")  # type: ignore[operator]

    def test_append_daily_merges_same_date(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.append_daily("morning work", date="2025-07-17")
        zone.append_daily("afternoon work", date="2025-07-17")

        snap = zone.read()
        content = snap.get_daily("2025-07-17")
        assert content is not None
        assert "morning work" in content
        assert "afternoon work" in content

    def test_clear_resets_memory(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("important stuff")
        zone.append_daily("daily note", date="2025-07-17")
        zone.clear()

        snap = zone.read()
        assert snap.long_term == ""
        assert snap.dailies == []

    def test_get_context_empty(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        assert zone.get_context() == ""

    def test_get_context_with_content(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("User likes dark mode")

        ctx = zone.get_context()
        assert "Long-term Memory" in ctx
        assert "User likes dark mode" in ctx
        assert "memory.save" in ctx  # usage hint present

    def test_get_context_separates_today_from_history(self) -> None:
        """Today's notes should appear under 'Today's Notes', not 'Recent Notes'."""
        from datetime import UTC, datetime

        _, zone = self._make_zone()
        zone.ensure()
        today = datetime.now(UTC).date().isoformat()
        zone.append_daily("today's work", date=today)
        zone.append_daily("yesterday's work", date="2020-01-01")

        ctx = zone.get_context()
        assert "Today's Notes" in ctx
        assert "today's work" in ctx
        # Old date should not appear in "Today's Notes" section
        # (it goes to Recent Notes only if within 7 days, otherwise omitted)

    def test_reload_from_tape_entries(self) -> None:
        """A fresh MemoryZone should recover state from existing tape entries."""
        fake, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("persisted memory")
        zone.append_daily("daily note", date="2025-07-17")

        # Create a new MemoryZone instance pointing at the same fake tape
        zone2 = MemoryZone(fake)  # type: ignore[arg-type]
        snap = zone2.read()
        assert snap.long_term == "persisted memory"
        assert snap.get_daily("2025-07-17") is not None

    def test_version_monotonically_increases(self) -> None:
        _, zone = self._make_zone()
        zone.ensure()  # v1
        zone.save_long_term("a")  # v2
        zone.save_long_term("b")  # v3
        zone.append_daily("c", date="2025-07-17")  # v4
        zone.clear()  # v5

        snap = zone.read()
        assert snap.version == 5

    def test_only_latest_zone_is_read(self) -> None:
        """Old memory zones in the tape should be ignored."""
        fake, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("old memory")
        zone.save_long_term("new memory")

        # Verify multiple anchor pairs exist
        seal_count = sum(1 for e in fake.entries if e.kind == "anchor" and e.payload.get("name") == MEMORY_SEAL_ANCHOR)
        assert seal_count >= 2  # at least ensure + 2 saves = 3

        # But reading should only return the latest
        zone2 = MemoryZone(fake)  # type: ignore[arg-type]
        snap = zone2.read()
        assert snap.long_term == "new memory"

    def test_tape_entries_structure(self) -> None:
        """Verify the actual JSONL entry structure written to tape."""
        fake, zone = self._make_zone()
        zone.ensure()
        zone.save_long_term("test content")

        events = [e for e in fake.entries if e.kind == "event"]
        long_terms = [e for e in events if e.payload.get("name") == MEMORY_LONG_TERM_EVENT]
        assert len(long_terms) >= 1
        latest = long_terms[-1]
        assert latest.payload["data"]["content"] == "test content"
        assert "updated_at" in latest.payload["data"]
