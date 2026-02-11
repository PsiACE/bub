import importlib
from dataclasses import dataclass, field

from bub.tools.schedule import run_scheduled_reminder

app_module = importlib.import_module("bub.app")


@dataclass
class _FakeBus:
    messages: list[object] = field(default_factory=list)

    async def publish_inbound(self, message: object) -> None:
        self.messages.append(message)


@dataclass
class _FakeRuntime:
    runtime_id: str
    bus: _FakeBus
    loop: object | None = None


def test_run_scheduled_reminder_routes_by_runtime_id(monkeypatch) -> None:
    runtime_a = _FakeRuntime(runtime_id="rid:a", bus=_FakeBus())
    runtime_b = _FakeRuntime(runtime_id="rid:b", bus=_FakeBus())
    runtimes = {
        runtime_a.runtime_id: runtime_a,
        runtime_b.runtime_id: runtime_b,
    }

    def _fake_get_runtime(runtime_id: str | None = None) -> _FakeRuntime:
        if runtime_id is None:
            return runtime_b
        return runtimes[runtime_id]

    monkeypatch.setattr(app_module, "get_runtime", _fake_get_runtime)

    run_scheduled_reminder("hello", "telegram:123", runtime_id=runtime_a.runtime_id)

    assert len(runtime_a.bus.messages) == 1
    assert len(runtime_b.bus.messages) == 0
