import importlib
from pathlib import Path

bootstrap_module = importlib.import_module("bub.app.bootstrap")


class _FakeSettings:
    def model_copy(self, update: dict[str, object]) -> "_FakeSettings":
        _ = update
        return self


def test_build_runtime_keeps_runtime_id_lookup_stable(monkeypatch, tmp_path: Path) -> None:
    created: list[object] = []

    class _FakeRuntime:
        def __init__(
            self,
            workspace: Path,
            settings: _FakeSettings,
            *,
            allowed_tools: set[str] | None = None,
            allowed_skills: set[str] | None = None,
        ) -> None:
            _ = (settings, allowed_tools, allowed_skills)
            self.runtime_id = f"rid:{workspace.name}"
            created.append(self)

    monkeypatch.setattr(bootstrap_module, "load_settings", lambda _workspace: _FakeSettings())
    monkeypatch.setattr(bootstrap_module, "AppRuntime", _FakeRuntime)
    monkeypatch.setattr(bootstrap_module, "_runtime", None)
    monkeypatch.setattr(bootstrap_module, "_runtimes", {})

    runtime_a = bootstrap_module.build_runtime(tmp_path / "a")
    runtime_b = bootstrap_module.build_runtime(tmp_path / "b")

    assert runtime_a is created[0]
    assert runtime_b is created[1]
    assert bootstrap_module.get_runtime() is runtime_b
    assert bootstrap_module.get_runtime(runtime_a.runtime_id) is runtime_a
    assert bootstrap_module.get_runtime(runtime_b.runtime_id) is runtime_b
