from __future__ import annotations

from pathlib import Path

from bub.skills.loader import (
    SkillMetadata,
    discover_hook_skills,
    discover_skills,
    load_bub_agent_profile,
    load_bub_agent_profile_file,
    skill_bub_agent_profile_path,
)


def _write_skill(root: Path, *, name: str, with_plugin: bool) -> None:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {name} skill",
                "---",
            ]
        ),
        encoding="utf-8",
    )
    if with_plugin:
        plugin_file = root / "agents" / "bub" / "plugin.py"
        plugin_file.parent.mkdir(parents=True)
        plugin_file.write_text(
            "\n".join(
                [
                    "from bub.hookspecs import hookimpl",
                    "",
                    "class DemoSkill:",
                    "    @hookimpl",
                    "    def resolve_session(self, message):",
                    "        return None",
                    "",
                    "plugin = DemoSkill()",
                ]
            ),
            encoding="utf-8",
        )


def _write_skill_with_frontmatter(root: Path, *, frontmatter_lines: list[str], with_plugin: bool) -> None:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("\n".join(frontmatter_lines), encoding="utf-8")
    if with_plugin:
        plugin_file = root / "agents" / "bub" / "plugin.py"
        plugin_file.parent.mkdir(parents=True)
        plugin_file.write_text(
            "\n".join(
                [
                    "from bub.hookspecs import hookimpl",
                    "",
                    "class DemoSkill:",
                    "    @hookimpl",
                    "    def resolve_session(self, message):",
                    "        return None",
                    "",
                    "plugin = DemoSkill()",
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
        with_plugin=True,
    )
    _write_skill(
        fake_home / ".agent" / "skills" / "demo",
        name="demo",
        with_plugin=True,
    )

    monkeypatch.setenv("HOME", str(fake_home))

    skills = discover_hook_skills(workspace)
    demo = next(skill for skill in skills if skill.name == "demo")
    assert demo.source == "project"
    assert demo.location.parent == workspace / ".agent" / "skills" / "demo"


def test_discover_hook_skills_filters_non_hook_skills(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _write_skill(
        workspace / ".agent" / "skills" / "no-plugin",
        name="no-plugin",
        with_plugin=False,
    )
    _write_skill(
        workspace / ".agent" / "skills" / "valid",
        name="valid",
        with_plugin=True,
    )

    names = [skill.name for skill in discover_hook_skills(workspace)]
    assert "valid" in names
    assert "no-plugin" not in names


def test_discover_skills_rejects_name_mismatch_with_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "actual-dir",
        frontmatter_lines=[
            "---",
            "name: other-name",
            "description: mismatch",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "other-name" not in names
    assert "actual-dir" not in names


def test_discover_skills_rejects_invalid_name_pattern(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "bad-name",
        frontmatter_lines=[
            "---",
            "name: bad--name",
            "description: invalid pattern",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "bad--name" not in names
    assert "bad-name" not in names


def test_discover_skills_rejects_missing_required_description(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "no-description",
        frontmatter_lines=[
            "---",
            "name: no-description",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "no-description" not in names


def test_discover_skills_rejects_invalid_metadata_type(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "bad-metadata",
        frontmatter_lines=[
            "---",
            "name: bad-metadata",
            "description: metadata must be string map",
            "metadata:",
            "  author: test",
            "  version: 1",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "bad-metadata" not in names


def test_discover_skills_accepts_spec_optional_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "spec-compliant",
        frontmatter_lines=[
            "---",
            "name: spec-compliant",
            "description: Valid skill metadata with optional fields included.",
            "license: Apache-2.0",
            "compatibility: Requires internet access and git.",
            "allowed-tools: Bash(git:*) Read",
            "metadata:",
            "  author: test",
            "  version: '1.0'",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "spec-compliant" in names


def test_discover_skills_rejects_unknown_frontmatter_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill_with_frontmatter(
        workspace / ".agent" / "skills" / "unknown-field",
        frontmatter_lines=[
            "---",
            "name: unknown-field",
            "description: contains unsupported top-level field.",
            "entrypoint: should-not-be-here",
            "---",
        ],
        with_plugin=True,
    )

    names = {skill.name for skill in discover_skills(workspace)}
    assert "unknown-field" not in names


def test_load_bub_agent_profile_by_skill_metadata(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir(parents=True)
    profile_path = skill_dir / "agents" / "bub" / "agent.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text("version: 1\nsystem_prompt: demo\n", encoding="utf-8")

    metadata = SkillMetadata(
        name="demo-skill",
        description="demo",
        location=skill_dir / "SKILL.md",
        source="project",
    )

    assert skill_bub_agent_profile_path(metadata) == profile_path
    profile = load_bub_agent_profile(metadata)
    assert profile["system_prompt"] == "demo"


def test_load_agent_profile_falls_back_when_missing(tmp_path: Path) -> None:
    profile = load_bub_agent_profile_file(tmp_path / "missing.yaml")
    assert profile == {}


def test_load_agent_profile_reads_prompt_fields(tmp_path: Path) -> None:
    path = tmp_path / "agent.yaml"
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "system_prompt: Runtime custom prompt",
                "continue_prompt: Continue from profile",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_bub_agent_profile_file(path)
    assert profile["system_prompt"] == "Runtime custom prompt"
    assert profile["continue_prompt"] == "Continue from profile"
