import importlib
from pathlib import Path

from bub.app.runtime import AppRuntime
from bub.skills.loader import SkillMetadata

runtime_module = importlib.import_module("bub.app.runtime")


def _build_runtime_stub(workspace: Path, *, allowed_skills: set[str] | None) -> AppRuntime:
    runtime = object.__new__(AppRuntime)
    runtime.workspace = workspace
    runtime._allowed_skills = allowed_skills  # type: ignore[attr-defined]
    return runtime


def test_discover_skills_filters_by_allowlist(monkeypatch, tmp_path: Path) -> None:
    alpha = SkillMetadata(name="alpha", description="a", location=tmp_path / "alpha.md", body="", source="project")
    beta = SkillMetadata(name="beta", description="b", location=tmp_path / "beta.md", body="", source="project")
    monkeypatch.setattr(runtime_module, "discover_skills", lambda _workspace: [alpha, beta])

    runtime = _build_runtime_stub(tmp_path, allowed_skills={"alpha"})
    names = [skill.name for skill in runtime.discover_skills()]
    assert names == ["alpha"]
