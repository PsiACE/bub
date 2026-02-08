"""Tests for skill discovery and prompt rendering."""

from pathlib import Path

from bub.skills import build_skills_prompt_section, discover_skills


def _write_skill(root: Path, folder: str, *, name: str, description: str) -> Path:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        (f"---\nname: {name}\ndescription: {description}\n---\n\nSkill instructions.\n"),
        encoding="utf-8",
    )
    return skill_file


def test_discover_skills_from_project_and_global(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project_root = workspace / ".agent" / "skills"
    project_file = _write_skill(project_root, "local_skill", name="local-skill", description="Project skill")

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    global_root = home / ".agent" / "skills"
    global_file = _write_skill(global_root, "global_skill", name="global-skill", description="Global skill")

    skills = discover_skills(workspace)
    by_name = {skill.name: skill for skill in skills}

    assert {"global-skill", "local-skill"}.issubset(set(by_name.keys()))
    assert by_name["local-skill"].location == project_file.resolve()
    assert by_name["global-skill"].location == global_file.resolve()


def test_project_skill_takes_precedence_on_name_conflict(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project_root = workspace / ".agent" / "skills"
    project_file = _write_skill(project_root, "fmt_local", name="formatter", description="Project formatter")

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    global_root = home / ".agent" / "skills"
    _write_skill(global_root, "fmt_global", name="formatter", description="Global formatter")

    skills = discover_skills(workspace)
    by_name = {skill.name: skill for skill in skills}
    assert "formatter" in by_name
    assert by_name["formatter"].description == "Project formatter"
    assert by_name["formatter"].location == project_file.resolve()


def test_build_skills_prompt_section_contains_available_skills_xml(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project_root = workspace / ".agent" / "skills"
    _write_skill(project_root, "db_skill", name="db-tune", description="Tune DB indexes & plans")

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    section = build_skills_prompt_section(workspace)

    assert section is not None
    assert "<available_skills>" in section
    assert "<name>db-tune</name>" in section
    assert "Tune DB indexes &amp; plans" in section


def test_builtin_skills_are_discoverable(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    skills = discover_skills(workspace)
    names = {skill.name for skill in skills}

    assert "skill-creator" in names
    assert "skill-installer" in names


def test_invalid_frontmatter_skill_is_skipped(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project_root = workspace / ".agent" / "skills"
    invalid_dir = project_root / "invalid_skill"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "SKILL.md").write_text(
        ("---\nname: invalid-skill\ndescription: [unterminated\n---\n\nBody.\n"),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    skills = discover_skills(workspace)
    names = {skill.name for skill in skills}

    assert "invalid-skill" not in names
