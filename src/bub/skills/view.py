"""Skill prompt rendering."""

from __future__ import annotations

from bub.skills.loader import SkillMetadata


def render_skill_prompt(skills: list[SkillMetadata]) -> str:
    """Render compact skill metadata for system prompt."""

    if not skills:
        return ""

    channel_skills: dict[str, SkillMetadata] = {}

    lines = ["<available_skills>"]
    for skill in skills:
        if skill.metadata and skill.metadata.get("channel"):
            channel_skills[skill.metadata["channel"]] = skill
        else:
            lines.extend([
                f"  <skill>",
                f"    <name>{skill.name}</name>",
                f"    <description>{skill.description}</description>",
                f"    <location>{skill.location}</location>",
                f"  </skill>",
            ])
    lines.append("</available_skills>")

    if channel_skills:
        channel_lines = ["<channel_skills>"]
        for channel, skill in channel_skills.items():
            channel_lines.extend([
                f"  <channel_skill>",
                f"    <name>{channel}</name>",
                f"    <description>{skill.description}</description>",
                f"    <location>{skill.location}</location>",
                f"  </channel_skill>",
            ])
        channel_lines.append("</channel_skills>")
        lines = channel_lines + lines
    return "\n".join(lines)
