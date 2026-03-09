from __future__ import annotations

import contextlib
from dataclasses import dataclass, field, replace
from typing import Any, Literal

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
    lifespan: contextlib.AbstractAsyncContextManager | None = None
    output_channel: str = ""

    def __post_init__(self) -> None:
        self.context.update({"channel": "$" + self.channel, "chat_id": self.chat_id})
        if not self.output_channel:  # output to the same channel by default
            self.output_channel = self.channel

    @property
    def context_str(self) -> str:
        """String representation of the context for prompt building."""
        return "|".join(f"{key}={value}" for key, value in self.context.items())

    @classmethod
    def from_batch(cls, batch: list[ChannelMessage]) -> ChannelMessage:
        """Create a single message by combining a batch of messages."""
        if not batch:
            raise ValueError("Batch cannot be empty")
        template = batch[-1]
        content = "\n".join(message.content for message in batch)
        return replace(template, content=content)
