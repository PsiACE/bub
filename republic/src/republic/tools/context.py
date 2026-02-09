"""Context payload for tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolContext:
    tape: str | None
    run_id: str
    meta: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
