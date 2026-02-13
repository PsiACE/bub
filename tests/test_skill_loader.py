from __future__ import annotations

from pathlib import Path

from bub.skills.loader import discover_hook_skills


def _write_skill(root: Path, *, name: str, kind: str, entrypoint: str) -> None:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"kind: {kind}",
                f"entrypoint: {entrypoint}",
                "---",
            ]
        ),
        encoding="utf-8",
    )


def test_discover_hook_skills_respects_project_over_global(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fake_home = tmp_path / "home"

    _write_skill(
        workspace / ".agent" / "skills" / "demo",
        name="demo",
        kind="model",
        entrypoint="project.demo:plugin",
    )
    _write_skill(
        fake_home / ".agent" / "skills" / "demo",
        name="demo",
        kind="model",
        entrypoint="global.demo:plugin",
    )

    monkeypatch.setenv("HOME", str(fake_home))

    skills = discover_hook_skills(workspace)
    demo = next(skill for skill in skills if skill.name == "demo")
    assert demo.source == "project"
    assert demo.metadata["entrypoint"] == "project.demo:plugin"


def test_discover_hook_skills_filters_non_hook_skills(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _write_skill(
        workspace / ".agent" / "skills" / "no-entrypoint",
        name="no-entrypoint",
        kind="model",
        entrypoint="",
    )
    _write_skill(
        workspace / ".agent" / "skills" / "valid",
        name="valid",
        kind="output",
        entrypoint="pkg.valid:plugin",
    )

    names = [skill.name for skill in discover_hook_skills(workspace)]
    assert "valid" in names
    assert "no-entrypoint" not in names
