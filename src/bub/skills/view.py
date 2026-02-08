"""Skill prompt rendering."""

from __future__ import annotations

from bub.skills.loader import SkillMetadata


def render_compact_skills(skills: list[SkillMetadata]) -> str:
    """Render compact skill metadata for system prompt."""

    if not skills:
        return ""

    lines = ["<skill_view>"]
    for skill in skills:
        lines.append(f"  - {skill.name}: {skill.description}")
    lines.append("</skill_view>")
    return "\n".join(lines)
