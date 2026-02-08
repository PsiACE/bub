"""Anchor models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnchorSummary:
    """Rendered anchor summary."""

    name: str
    state: dict[str, object]
