"""Builtin memory hook implementation."""

from __future__ import annotations

from bub.envelope import content_of
from bub.hookspecs import hookimpl
from bub.skills.builtin.common import read_turn
from bub.types import Envelope, State


class MemoryTapeSkill:
    def __init__(self) -> None:
        self._state_by_session: dict[str, State] = {}

    @hookimpl
    def load_state(self, session_id: str) -> State:
        state = self._state_by_session.get(session_id, {"turn": 0})
        return dict(state)

    @hookimpl
    def save_state(self, session_id: str, state: State, message: Envelope, model_output: str) -> None:
        state["turn"] = read_turn(state) + 1
        state["last_user"] = content_of(message)
        state["last_assistant"] = model_output
        self._state_by_session[session_id] = dict(state)


plugin = MemoryTapeSkill()
