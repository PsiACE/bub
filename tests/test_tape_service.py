from dataclasses import dataclass

from bub.tape.service import TapeService


@dataclass
class FakeEntry:
    kind: str
    payload: dict[str, object]


class FakeTape:
    def __init__(self) -> None:
        self.name = "fake"
        self.entries: list[FakeEntry] = [FakeEntry("anchor", {"name": "session/start", "state": {"owner": "human"}})]
        self.reset_calls = 0

    def read_entries(self) -> list[FakeEntry]:
        return list(self.entries)

    def handoff(self, name: str, state: dict[str, object] | None = None) -> list[FakeEntry]:
        entry = FakeEntry("anchor", {"name": name, "state": state or {}})
        self.entries.append(entry)
        return [entry]

    def append(self, entry: object) -> None:
        kind = getattr(entry, "kind", "")
        payload = getattr(entry, "payload", {})
        self.entries.append(FakeEntry(str(kind), dict(payload)))

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
    anchor_names = [entry.payload["name"] for entry in anchors]
    assert "session/start" in anchor_names
    assert "memory/open" in anchor_names
    assert "memory/seal" in anchor_names
