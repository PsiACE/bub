"""Shared core dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DetectedCommand:
    """Detected command parsed from a line."""

    kind: str  # internal|shell
    raw: str
    name: str
    args_tokens: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedAssistantMessage:
    """Assistant output split between text and command lines."""

    visible_lines: list[str]
    commands: list[DetectedCommand]
