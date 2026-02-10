"""Channel bus event models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    """Message received from an external channel."""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def session_id(self) -> str:
        return f"{self.channel}:{self.chat_id}"

    def render(self) -> str:
        data = {"message": self.content, **self.metadata, "sender_id": self.sender_id}
        return json.dumps(data, ensure_ascii=False)


@dataclass(frozen=True)
class OutboundMessage:
    """Message to be delivered to one external channel."""

    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to_message_id: int | None = None
