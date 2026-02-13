"""Builtin output hooks."""

from __future__ import annotations

from bub.envelope import field_of
from bub.hookspecs import hookimpl
from bub.types import Envelope, State


class OutputStdoutSkill:
    @hookimpl
    def render_outbound(self, message: Envelope, session_id: str, state: State, model_output: str) -> list[Envelope]:
        _ = state
        channel = field_of(message, "channel", "stdout")
        chat_id = field_of(message, "chat_id", "local")
        return [
            {
                "channel": channel,
                "chat_id": chat_id,
                "content": model_output,
                "metadata": {"session_id": session_id},
            }
        ]

    @hookimpl
    def dispatch_outbound(self, message: Envelope) -> bool:
        if field_of(message, "channel", "stdout") != "stdout":
            return False
        print(field_of(message, "content", ""))
        return True


plugin = OutputStdoutSkill()
