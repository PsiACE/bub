"""Tests for agent loop stopping behavior."""

from __future__ import annotations

from dataclasses import dataclass

from bub.runtime.loop import AgentLoop
from bub.runtime.router import AssistantResult, RouteResult


@dataclass
class _FakeSession:
    results: list[AssistantResult]

    def __post_init__(self) -> None:
        self._idx = 0

    def handle_input(self, raw: str, *, origin: str = "human") -> RouteResult:
        return RouteResult(agent_input=raw, enter_agent=True, exit_requested=False, done_requested=False)

    def agent_respond(self, on_event=None) -> str:
        return "assistant"

    def interpret_assistant(self, raw: str) -> AssistantResult:
        result = self.results[self._idx]
        self._idx += 1
        return result


@dataclass
class _FakeTape:
    loops: list[str]
    assistant_messages: list[str]
    context_messages: list[str]

    def record_loop(self, loop_id: str, status: str, *, detail: str | None = None) -> None:
        self.loops.append(status)

    def record_assistant_message(self, content: str) -> None:
        self.assistant_messages.append(content)

    def record_context_message(self, content: str) -> None:
        self.context_messages.append(content)

    def record_tool_event(self, kind: str, payload: dict) -> None:
        pass


def test_agent_loop_stops_on_plain_text_without_followup() -> None:
    session = _FakeSession(
        results=[
            AssistantResult(
                followup_input="",
                exit_requested=False,
                done_requested=False,
                visible_text="final answer",
            )
        ]
    )
    tape = _FakeTape(loops=[], assistant_messages=[], context_messages=[])

    loop = AgentLoop(session, tape)
    loop._run_loop()

    assert tape.loops == ["start", "idle"]
    assert tape.assistant_messages == ["final answer"]
    assert tape.context_messages == []


def test_agent_loop_continues_when_followup_exists() -> None:
    session = _FakeSession(
        results=[
            AssistantResult(
                followup_input='<cmd name="fs.read" status="ok">\n...\n</cmd>',
                exit_requested=False,
                done_requested=False,
                visible_text="",
            ),
            AssistantResult(
                followup_input="",
                exit_requested=False,
                done_requested=True,
                visible_text="",
            ),
        ]
    )
    tape = _FakeTape(loops=[], assistant_messages=[], context_messages=[])

    loop = AgentLoop(session, tape)
    loop._run_loop()

    assert tape.loops == ["start", "done"]
    assert len(tape.context_messages) == 1
    assert '<cmd name="fs.read"' in tape.context_messages[0]
