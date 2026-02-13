"""Builtin input bus hooks."""

from __future__ import annotations

from bub.bus import MessageBus
from bub.envelope import normalize_envelope
from bub.hookspecs import hookimpl
from bub.types import Envelope


class InputBusSkill:
    @hookimpl
    def provide_bus(self) -> MessageBus:
        return MessageBus()

    @hookimpl
    def normalize_inbound(self, message: Envelope) -> Envelope:
        envelope = normalize_envelope(message)
        content = str(envelope.get("content", "")).strip()
        metadata = envelope.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.setdefault("normalized", True)
        envelope["content"] = content
        envelope["metadata"] = metadata
        return envelope

    @hookimpl
    def resolve_session(self, message: Envelope) -> str | None:
        envelope = normalize_envelope(message)
        channel = envelope.get("channel")
        chat_id = envelope.get("chat_id")
        if channel is None or chat_id is None:
            return None
        return f"{channel}:{chat_id}"


plugin = InputBusSkill()
