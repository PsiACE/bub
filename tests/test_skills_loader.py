from pathlib import Path

from bub.skills.loader import discover_skills


def test_discover_and_load_project_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agent" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: demo-skill\ndescription: demo skill\n---\n\n# Demo\n",
        encoding="utf-8",
    )

    skills = discover_skills(tmp_path)
    names = [skill.name for skill in skills]
    assert "demo-skill" in names
