"""Builtin model hook implementation."""

from __future__ import annotations

from bub.envelope import content_of
from bub.hookspecs import hookimpl
from bub.skills.builtin.common import read_turn
from bub.types import Envelope, State


class EchoModelSkill:
    @hookimpl
    def build_prompt(self, message: Envelope, session_id: str, state: State) -> str:
        _ = session_id
        prefix = str(state.get("prompt_prefix", ""))
        return f"{prefix}{content_of(message)}"

    @hookimpl
    def run_model(self, prompt: str, session_id: str, state: State) -> str:
        turn = read_turn(state) + 1
        return f"[{session_id}] turn={turn} {prompt}"


plugin = EchoModelSkill()
