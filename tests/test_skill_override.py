from __future__ import annotations

from pathlib import Path

import pytest
import typer

from bub.framework import BubFramework


def _write_project_override_skill(workspace: Path) -> None:
    package = workspace / "project_plugins"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "override.py").write_text(
        "\n".join(
            [
                "import typer",
                "",
                "from bub.bus import MessageBus",
                "from bub.hookspecs import hookimpl",
                "",
                "class ProjectBus(MessageBus):",
                "    pass",
                "",
                "class ProjectOverrideSkill:",
                "    @hookimpl",
                "    def provide_bus(self):",
                "        return ProjectBus()",
                "",
                "    @hookimpl",
                "    def register_cli_commands(self, app):",
                "        @app.command('project-ping')",
                "        def project_ping():",
                "            typer.echo('pong')",
                "",
                "plugin = ProjectOverrideSkill()",
            ]
        ),
        encoding="utf-8",
    )

    skill_dir = workspace / ".agent" / "skills" / "project-override"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: project-override",
                "description: project overrides bus and cli hooks",
                "kind: hook",
                "entrypoint: project_plugins.override:plugin",
                "---",
            ]
        ),
        encoding="utf-8",
    )


def test_project_skill_can_override_builtin_bus(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_project_override_skill(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    framework = BubFramework(tmp_path)
    framework.load_skills()
    bus = framework.create_bus()

    assert bus.__class__.__name__ == "ProjectBus"


def test_project_skill_can_extend_cli_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_project_override_skill(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    framework = BubFramework(tmp_path)
    framework.load_skills()
    app = typer.Typer()

    framework.register_cli_commands(app)

    names = {command.name for command in app.registered_commands}
    assert "project-ping" in names
