import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Self

type MessageKind = Literal["error", "normal", "command"]


@dataclass
class ChannelMessage:
    """Structured message data from channels to framework."""

    session_id: str
    channel: str
    content: str
    chat_id: str = "default"
    is_active: bool = False
    kind: MessageKind = "normal"
    context: dict[str, Any] = field(default_factory=dict)
    on_start: Callable[[Self], Any] | None = None
    on_finish: Callable[[Self], Any] | None = None
    output_channel: str = ""

    def __post_init__(self) -> None:
        self.context.update({"channel": "$" + self.channel, "chat_id": self.chat_id})
        if not self.output_channel:  # output to the same channel by default
            self.output_channel = self.channel

    @property
    def context_str(self) -> str:
        """String representation of the context for prompt building."""
        return json.dumps(self.context, ensure_ascii=False)[1:-1]
