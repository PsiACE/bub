import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True)
class ChannelMessage:
    """Structured message data from channels to framework."""

    session_id: str
    channel: str
    content: str
    chat_id: str = "default"
    is_active: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    on_start: Callable[[Self], Coroutine[None, None, None]] | None = None
    on_finish: Callable[[Self], Coroutine[None, None, None]] | None = None

    def __post_init__(self) -> None:
        self.context.update({"channel": "$" + self.channel, "chat_id": self.chat_id})

    @property
    def context_str(self) -> str:
        """String representation of the context for prompt building."""
        return json.dumps(self.context, ensure_ascii=False)[1:-1]
