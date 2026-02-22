from __future__ import annotations

from bub.envelope import content_of
from bub.hookspecs import hookimpl


class StatefulHooksSkill:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, object]] = {}

    @hookimpl
    def load_state(self, session_id: str) -> dict[str, object]:
        return dict(self._states.get(session_id, {"turn": 0}))

    @hookimpl
    def build_prompt(self, message: object, session_id: str, state: dict[str, object]) -> str:
        _ = session_id
        _ = state
        return content_of(message)

    @hookimpl
    def run_model(self, prompt: str, session_id: str, state: dict[str, object]) -> str:
        turn = int(state.get("turn", 0)) + 1
        return f"[{session_id}] turn={turn} {prompt}"

    @hookimpl
    def save_state(
        self,
        session_id: str,
        state: dict[str, object],
        message: object,
        model_output: str,
    ) -> None:
        _ = message, model_output
        state["turn"] = int(state.get("turn", 0)) + 1
        self._states[session_id] = dict(state)


adapter = StatefulHooksSkill()
