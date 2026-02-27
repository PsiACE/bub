from dataclasses import dataclass

from bub.tape.service import TapeService


@dataclass
class FakeEntry:
    id: int
    kind: str
    payload: dict[str, object]
    meta: dict[str, object]


class FakeTape:
    class _Query:
        def __init__(self, tape: "FakeTape") -> None:
            self._tape = tape

        def all(self) -> list[FakeEntry]:
            return list(self._tape.entries)

    def __init__(self) -> None:
        self.name = "fake"
        self.entries: list[FakeEntry] = [
            FakeEntry(
                id=1,
                kind="anchor",
                payload={"name": "session/start", "state": {"owner": "human"}},
                meta={},
            )
        ]
        self.reset_calls = 0
        self.query = self._Query(self)

    def handoff(self, name: str, state: dict[str, object] | None = None) -> list[FakeEntry]:
        entry = FakeEntry(
            id=len(self.entries) + 1,
            kind="anchor",
            payload={"name": name, "state": state or {}},
            meta={},
        )
        self.entries.append(entry)
        return [entry]

    def reset(self) -> None:
        self.reset_calls += 1
        self.entries = []


def test_reset_rebuilds_bootstrap_anchor() -> None:
    service = TapeService.__new__(TapeService)
    fake_tape = FakeTape()
    service._tape = fake_tape  # type: ignore[attr-defined]
    service._store = None  # type: ignore[attr-defined]

    result = service.reset()

    assert result == "ok"
    assert fake_tape.reset_calls == 1
    anchors = [entry for entry in fake_tape.entries if entry.kind == "anchor"]
    assert len(anchors) == 1
    assert anchors[0].payload["name"] == "session/start"


def test_search_supports_fuzzy_typo_matching() -> None:
    service = TapeService.__new__(TapeService)
    fake_tape = FakeTape()
    fake_tape.entries.extend((
        FakeEntry(
            id=2,
            kind="message",
            payload={"role": "assistant", "content": "Please review the database migration plan."},
            meta={"source": "assistant"},
        ),
        FakeEntry(
            id=3,
            kind="message",
            payload={"role": "assistant", "content": "Unrelated note"},
            meta={},
        ),
    ))
    service._tape = fake_tape  # type: ignore[attr-defined]

    matches = service.search("databse migrtion", limit=5)

    assert len(matches) == 1
    assert matches[0].id == 2


def test_search_respects_limit_for_exact_match() -> None:
    service = TapeService.__new__(TapeService)
    fake_tape = FakeTape()
    fake_tape.entries.extend((
        FakeEntry(
            id=2,
            kind="message",
            payload={"role": "assistant", "content": "Alpha report generated"},
            meta={},
        ),
        FakeEntry(
            id=3,
            kind="message",
            payload={"role": "assistant", "content": "Alpha follow-up details"},
            meta={},
        ),
    ))
    service._tape = fake_tape  # type: ignore[attr-defined]

    matches = service.search("alpha", limit=1)

    assert len(matches) == 1
    assert matches[0].id == 3
