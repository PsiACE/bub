"""Skill discovery and Bub runtime adapter loading."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_SKILLS_DIR = ".agents/skills"
SKILL_FILE_NAME = "SKILL.md"
SKILL_SOURCES = ("project", "global", "builtin")
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class SkillMetadata:
    """Discovered skill metadata."""

    name: str
    description: str
    location: Path
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def body(self) -> str:
        front_matter_pattern = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
        try:
            content = self.location.read_text(encoding="utf-8")
        except OSError:
            return ""
        return front_matter_pattern.sub("", content, count=1).strip()


def discover_skills(workspace_path: Path) -> list[SkillMetadata]:
    """Discover skills from project, global, and builtin roots with override precedence."""

    skills_by_name: dict[str, SkillMetadata] = {}
    for root, source in _iter_skill_roots(workspace_path):
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            metadata = _read_skill(skill_dir, source=source)
            if metadata is None:
                continue
            key = metadata.name.casefold()
            if key not in skills_by_name:
                skills_by_name[key] = metadata

    return sorted(skills_by_name.values(), key=lambda item: item.name.casefold())


def _read_skill(skill_dir: Path, *, source: str) -> SkillMetadata | None:
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None

    metadata = _parse_frontmatter(content)
    if not _is_valid_frontmatter(skill_dir=skill_dir, metadata=metadata):
        return None
    name = str(metadata["name"]).strip()
    description = str(metadata["description"]).strip()

    return SkillMetadata(
        name=name,
        description=description,
        location=skill_file.resolve(),
        source=source,
        metadata={str(key).casefold(): value for key, value in metadata.items() if key is not None},
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            payload = "\n".join(lines[1:idx])
            try:
                parsed = yaml.safe_load(payload)
            except yaml.YAMLError:
                parsed = {}
            body = "\n".join(lines[idx + 1 :])
            if isinstance(parsed, dict):
                return {str(key).lower(): value for key, value in parsed.items()}, body
            return {}, body
    return {}, content


def _is_valid_frontmatter(*, skill_dir: Path, metadata: dict[str, object]) -> bool:
    name = metadata.get("name")
    description = metadata.get("description")
    return (
        _is_valid_name(name=name, skill_dir=skill_dir)
        and _is_valid_description(description)
        and _is_valid_metadata_field(metadata.get("metadata"))
    )


def _is_valid_name(*, name: object, skill_dir: Path) -> bool:
    if not isinstance(name, str):
        return False
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 64:
        return False
    if normalized_name != skill_dir.name:
        return False
    return SKILL_NAME_PATTERN.fullmatch(normalized_name) is not None


def _is_valid_description(description: object) -> bool:
    if not isinstance(description, str):
        return False
    normalized = description.strip()
    return bool(normalized) and len(normalized) <= 1024


def _is_valid_metadata_field(metadata_field: object) -> bool:
    if metadata_field is None:
        return True
    if not isinstance(metadata_field, dict):
        return False
    return all(isinstance(key, str) and isinstance(value, str) for key, value in metadata_field.items())


def _builtin_skills_root() -> Path:
    return Path(__file__).resolve().parent.parent / "bub_skills"


def _iter_skill_roots(workspace_path: Path) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    for source in SKILL_SOURCES:
        if source == "project":
            roots.append((workspace_path / PROJECT_SKILLS_DIR, source))
        elif source == "global":
            roots.append((Path.home() / PROJECT_SKILLS_DIR, source))
        elif source == "builtin":
            roots.append((_builtin_skills_root(), source))
    return roots


def render_skills_prompt(skills: list[SkillMetadata], expanded_skills: Collection[str] = ()) -> str:
    if not skills:
        return ""
    lines = ["<available_skills>"]
    for skill in skills:
        line = f"- [{skill.name}]({skill.location}): {skill.description}"
        if skill.name in expanded_skills:
            body = skill.body()
            if body:
                line += f"\n{body}"
        lines.append(line)
    lines.append("</available_skills>")
    return "\n".join(lines)
