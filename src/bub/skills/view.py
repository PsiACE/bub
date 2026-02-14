"""Skill prompt rendering."""

from __future__ import annotations

from bub.skills.loader import SkillMetadata


def render_compact_skills(skills: list[SkillMetadata]) -> str:
    """Render compact skill metadata for system prompt."""

    if not skills:
        return ""

    lines = ["<available_skills>"]
    for skill in skills:
        lines.extend([
            f"  <skill>",
            f"    <name>{skill.name}</name>",
            f"    <description>{skill.description}</description>",
            f"    <location>{skill.location}</location>",
            f"  </skill>",
        ])
    lines.append("</available_skills>")
    return "\n".join(lines)
