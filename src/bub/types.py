"""Framework-neutral data aliases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type Envelope = Any
type State = dict[str, Any]


@dataclass(frozen=True)
class TurnResult:
    """Result of one complete message turn."""

    session_id: str
    prompt: str
    model_output: str
    outbounds: list[Envelope] = field(default_factory=list)
