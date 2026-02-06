"""Tests for CLI app commands."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from bub.runtime.router import AssistantResult, RouteResult

cli_app = importlib.import_module("bub.cli.app")


@dataclass
class _FakeTape:
    tool_events: list[tuple[str, dict]] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)

    def record_tool_event(self, kind: str, payload: dict) -> None:
        self.tool_events.append((kind, payload))

    def record_assistant_message(self, content: str) -> None:
        self.assistant_messages.append(content)


@dataclass
class _FakeSession:
    route_result: RouteResult
    assistant_result: AssistantResult

    handle_calls: int = 0
    respond_calls: int = 0
    interpret_calls: int = 0

    def handle_input(self, raw: str, *, origin: str = "human") -> RouteResult:
        _ = (raw, origin)
        self.handle_calls += 1
        return self.route_result

    def agent_respond(self, on_event=None) -> str:
        self.respond_calls += 1
        if on_event is not None:
            on_event(type("Event", (), {"kind": "tool_call", "payload": {"name": "fs_read"}})())
        return "raw assistant"

    def interpret_assistant(self, raw: str) -> AssistantResult:
        _ = raw
        self.interpret_calls += 1
        return self.assistant_result


@dataclass
class _FakeRuntime:
    session: _FakeSession
    tape: _FakeTape


@dataclass
class _FakeRenderer:
    infos: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


def test_run_performs_single_request_response(monkeypatch, tmp_path: Path) -> None:
    session = _FakeSession(
        route_result=RouteResult(agent_input="request", enter_agent=True, exit_requested=False, done_requested=False),
        assistant_result=AssistantResult(
            followup_input='<cmd name="bash" status="ok">\\n...\\n</cmd>',
            exit_requested=False,
            done_requested=False,
            visible_text="final response",
        ),
    )
    tape = _FakeTape()
    runtime = _FakeRuntime(session=session, tape=tape)
    renderer = _FakeRenderer()

    monkeypatch.setattr(cli_app, "renderer", renderer)
    monkeypatch.setattr(cli_app, "_build_runtime", lambda workspace_path, model, max_tokens: runtime)

    cli_app.run("say hi", workspace=tmp_path)

    assert session.handle_calls == 1
    assert session.respond_calls == 1
    assert session.interpret_calls == 1
    assert renderer.infos == ["final response"]
    assert tape.assistant_messages == ["final response"]
    assert tape.tool_events == [("tool_call", {"name": "fs_read"})]


def test_run_skips_agent_when_route_does_not_enter_agent(monkeypatch, tmp_path: Path) -> None:
    session = _FakeSession(
        route_result=RouteResult(agent_input="", enter_agent=False, exit_requested=False, done_requested=False),
        assistant_result=AssistantResult(
            followup_input="",
            exit_requested=False,
            done_requested=False,
            visible_text="should not appear",
        ),
    )
    runtime = _FakeRuntime(session=session, tape=_FakeTape())
    renderer = _FakeRenderer()

    monkeypatch.setattr(cli_app, "renderer", renderer)
    monkeypatch.setattr(cli_app, "_build_runtime", lambda workspace_path, model, max_tokens: runtime)

    cli_app.run("$tape.info", workspace=tmp_path)

    assert session.handle_calls == 1
    assert session.respond_calls == 0
    assert session.interpret_calls == 0
    assert renderer.infos == []


def test_run_skips_agent_when_done_requested(monkeypatch, tmp_path: Path) -> None:
    session = _FakeSession(
        route_result=RouteResult(agent_input="", enter_agent=True, exit_requested=False, done_requested=True),
        assistant_result=AssistantResult(
            followup_input="",
            exit_requested=False,
            done_requested=False,
            visible_text="should not appear",
        ),
    )
    runtime = _FakeRuntime(session=session, tape=_FakeTape())
    renderer = _FakeRenderer()

    monkeypatch.setattr(cli_app, "renderer", renderer)
    monkeypatch.setattr(cli_app, "_build_runtime", lambda workspace_path, model, max_tokens: runtime)

    cli_app.run("$done", workspace=tmp_path)

    assert session.handle_calls == 1
    assert session.respond_calls == 0
    assert session.interpret_calls == 0
    assert renderer.infos == []


def test_run_skips_agent_when_exit_requested(monkeypatch, tmp_path: Path) -> None:
    session = _FakeSession(
        route_result=RouteResult(agent_input="", enter_agent=True, exit_requested=True, done_requested=False),
        assistant_result=AssistantResult(
            followup_input="",
            exit_requested=False,
            done_requested=False,
            visible_text="should not appear",
        ),
    )
    runtime = _FakeRuntime(session=session, tape=_FakeTape())
    renderer = _FakeRenderer()

    monkeypatch.setattr(cli_app, "renderer", renderer)
    monkeypatch.setattr(cli_app, "_build_runtime", lambda workspace_path, model, max_tokens: runtime)

    cli_app.run("$quit", workspace=tmp_path)

    assert session.handle_calls == 1
    assert session.respond_calls == 0
    assert session.interpret_calls == 0
    assert renderer.infos == []
