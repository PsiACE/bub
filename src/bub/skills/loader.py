"""Skill discovery and hook plugin loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

PROJECT_SKILLS_DIR = ".agent/skills"
SKILL_FILE_NAME = "SKILL.md"
HOOK_SKILL_KINDS = frozenset({"hook", "model", "memory", "output", "bus", "tool", "channel", "command"})
SKILL_SOURCES = ("project", "global", "builtin")


@dataclass(frozen=True)
class SkillMetadata:
    """Discovered skill metadata."""

    name: str
    description: str
    location: Path
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


def discover_hook_skills(workspace_path: Path) -> list[SkillMetadata]:
    """Discover skills with hook entrypoints."""

    results: list[SkillMetadata] = []
    for skill in discover_skills(workspace_path):
        entrypoint = skill.metadata.get("entrypoint")
        kind = str(skill.metadata.get("kind") or "").strip().lower()
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            continue
        if kind not in HOOK_SKILL_KINDS:
            continue
        results.append(skill)
    return results


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


def load_skill_plugin(skill: SkillMetadata) -> object:
    """Load plugin object from one skill entrypoint."""

    entrypoint = skill.metadata.get("entrypoint")
    if not isinstance(entrypoint, str):
        raise TypeError(f"{skill.name}: entrypoint must be string")

    module_name, sep, attr_name = entrypoint.partition(":")
    if not sep or not module_name or not attr_name:
        raise ValueError(f"{skill.name}: invalid entrypoint format '{entrypoint}'")

    module = import_module(module_name)
    plugin = getattr(module, attr_name)
    return plugin


def _read_skill(skill_dir: Path, *, source: str) -> SkillMetadata | None:
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None

    metadata = _parse_frontmatter(content)
    name = str(metadata.get("name") or skill_dir.name).strip()
    description = str(metadata.get("description") or "No description provided.").strip()
    if not name:
        return None

    return SkillMetadata(
        name=name,
        description=description,
        location=skill_file.resolve(),
        source=source,
        metadata={str(key).casefold(): value for key, value in metadata.items() if key is not None},
    )


def _parse_frontmatter(content: str) -> dict[str, object]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            payload = "\n".join(lines[1:idx])
            try:
                parsed = yaml.safe_load(payload)
            except yaml.YAMLError:
                return {}
            if isinstance(parsed, dict):
                return {str(key).lower(): value for key, value in parsed.items()}
            return {}
    return {}


def _builtin_skills_root() -> Path:
    return Path(__file__).resolve().parent / "builtin"


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
