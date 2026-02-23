"""Skill discovery and loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

PROJECT_SKILLS_DIR = ".agent/skills"
SKILL_FILE_NAME = "SKILL.md"


@dataclass(frozen=True)
class SkillMetadata:
    """Skill metadata used in compact prompt view."""

    name: str
    description: str
    location: Path
    body: str
    metadata: dict[str, Any] | None = None
    source: str = "unknown"


def discover_skills(workspace_path: Path) -> list[SkillMetadata]:
    """Discover skills from project, global, and built-in roots."""

    ordered_roots = [
        (workspace_path / PROJECT_SKILLS_DIR, "project"),
        (Path.home() / PROJECT_SKILLS_DIR, "global"),
        (_builtin_skills_root(), "builtin"),
    ]

    by_name: dict[str, SkillMetadata] = {}
    for root, source in ordered_roots:
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            metadata = _read_skill(skill_dir, source=source)
            if metadata is None:
                continue
            key = metadata.name.casefold()
            if key not in by_name:
                by_name[key] = metadata

    return sorted(by_name.values(), key=lambda item: item.name.casefold())


def _read_skill(skill_dir: Path, *, source: str) -> SkillMetadata | None:
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None

    metadata, body = _parse_frontmatter(content)
    name = str(metadata.get("name") or skill_dir.name).strip()
    description = str(metadata.get("description") or "No description provided.").strip()
    meta = cast(dict[str, Any], metadata.get("metadata"))

    if not name:
        return None

    return SkillMetadata(
        name=name, description=description, location=skill_file.resolve(), source=source, metadata=meta, body=body
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


def _builtin_skills_root() -> Path:
    return Path(__file__).resolve().parent
