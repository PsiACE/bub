from __future__ import annotations

from pathlib import Path

import typer

from bub.framework import BubFramework


def _write_project_override_skill(workspace: Path) -> None:
    skill_dir = workspace / ".agent" / "skills" / "project-override"
    plugin_file = skill_dir / "agents" / "bub" / "plugin.py"
    plugin_file.parent.mkdir(parents=True)
    plugin_file.write_text(
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

    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: project-override",
                "description: project overrides bus and cli hooks",
                "---",
            ]
        ),
        encoding="utf-8",
    )


def test_project_skill_can_override_builtin_bus(tmp_path: Path) -> None:
    _write_project_override_skill(tmp_path)

    framework = BubFramework(tmp_path)
    framework.load_skills()
    bus = framework.create_bus()

    assert bus.__class__.__name__ == "ProjectBus"


def test_project_skill_can_extend_cli_commands(tmp_path: Path) -> None:
    _write_project_override_skill(tmp_path)

    framework = BubFramework(tmp_path)
    framework.load_skills()
    app = typer.Typer()

    framework.register_cli_commands(app)

    names = {command.name for command in app.registered_commands}
    assert "project-ping" in names
