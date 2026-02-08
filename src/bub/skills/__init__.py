"""Agent skill discovery and prompt rendering helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from html import escape
from pathlib import Path

import yaml

DEFAULT_SKILL_DESCRIPTION = "No description provided."
FRONTMATTER_DELIMITER = "---"
PROJECT_SKILLS_DIR = ".agent/skills"
SKILL_FILE_NAME = "SKILL.md"


@dataclass(frozen=True)
class SkillMetadata:
    """Skill metadata used in the system prompt."""

    name: str
    description: str
    location: Path


def discover_skills(workspace_path: Path | None = None) -> list[SkillMetadata]:
    """Discover skills from project, global, and builtin directories.

    Precedence when names collide: project > global > builtin.
    """
    skills_by_name: dict[str, SkillMetadata] = {}
    for skills_root in _discover_skill_roots(workspace_path):
        for skill_dir in _iter_skill_dirs(skills_root):
            skill = _read_skill_metadata(skill_dir)
            if skill is None:
                continue
            key = skill.name.casefold()
            if key not in skills_by_name:
                skills_by_name[key] = skill
    return sorted(skills_by_name.values(), key=lambda item: item.name.casefold())


def build_skills_prompt_section(workspace_path: Path | None = None) -> str | None:
    """Build a prompt section containing available skill metadata."""
    skills = discover_skills(workspace_path)
    if not skills:
        return None
    xml = render_available_skills_xml(skills)
    return (
        "Agent Skills are available.\n"
        "Only load a skill when it is relevant to the user request.\n"
        "Before using a skill, read the full SKILL.md file at its location.\n"
        f"{xml}"
    )


def render_available_skills_xml(skills: list[SkillMetadata]) -> str:
    """Render discovered skills as `<available_skills>` XML."""
    lines = ["<available_skills>"]
    for skill in skills:
        lines.extend([
            "  <skill>",
            f"    <name>{escape(skill.name)}</name>",
            f"    <description>{escape(skill.description)}</description>",
            f"    <location>{escape(str(skill.location))}</location>",
            "  </skill>",
        ])
    lines.append("</available_skills>")
    return "\n".join(lines)


def _discover_skill_roots(workspace_path: Path | None) -> Iterator[Path]:
    project_root = _find_project_skills_root(workspace_path)
    if project_root is not None:
        yield project_root.resolve()

    global_root = _global_skills_root()
    if global_root.is_dir():
        yield global_root.resolve()

    builtin_root = _builtin_skills_root()
    if builtin_root.is_dir():
        yield builtin_root.resolve()


def _find_project_skills_root(workspace_path: Path | None) -> Path | None:
    start = Path.cwd() if workspace_path is None else workspace_path
    if not start.is_dir():
        start = start.parent
    start = start.resolve()

    for parent in [start, *start.parents]:
        candidate = parent / PROJECT_SKILLS_DIR
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _global_skills_root() -> Path:
    return Path.home() / PROJECT_SKILLS_DIR


def _builtin_skills_root() -> Path:
    return Path(__file__).resolve().parent


def _iter_skill_dirs(skills_root: Path) -> list[Path]:
    try:
        candidates = sorted(skills_root.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    return [path for path in candidates if path.is_dir()]


def _read_skill_metadata(skill_dir: Path) -> SkillMetadata | None:
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter = _parse_frontmatter(content)
    if frontmatter is None:
        return None

    name = _normalize_metadata_value(frontmatter.get("name")) or skill_dir.name
    description = _normalize_metadata_value(frontmatter.get("description")) or DEFAULT_SKILL_DESCRIPTION

    return SkillMetadata(
        name=name,
        description=description,
        location=skill_file.resolve(),
    )


def _extract_frontmatter(content: str) -> str | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None

    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:idx])
    return None


def _parse_frontmatter(content: str) -> dict[str, object] | None:
    raw_frontmatter = _extract_frontmatter(content)
    if raw_frontmatter is None:
        return None

    try:
        parsed = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError:
        return None

    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        return None

    metadata: dict[str, object] = {}
    for key, value in parsed.items():
        if isinstance(key, str):
            metadata[key.lower()] = value
    return metadata


def _normalize_metadata_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (bool, int, float)):
        return str(value).strip()
    return ""


__all__ = [
    "SkillMetadata",
    "build_skills_prompt_section",
    "discover_skills",
    "render_available_skills_xml",
]
