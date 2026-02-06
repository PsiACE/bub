"""Tests for agent tool-result contract and stagnation recovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, ClassVar

from bub.agent import Context
from bub.agent.core import Agent, ToolEvent


def _tool_call_response(*, name: str, arguments: str = "{}") -> object:
    function = SimpleNamespace(name=name, arguments=arguments)
    tool_call = SimpleNamespace(id="call-id", type="function", function=function)
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _text_response(text: str) -> object:
    message = SimpleNamespace(content=text, tool_calls=[])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


@dataclass
class _FakeChat:
    responses: list[object]
    forced_text_when_no_tools: str

    def raw(self, *, messages: list[dict[str, Any]], tools: list[Any], max_tokens: int | None = None) -> object:
        _ = (messages, max_tokens)
        if not tools:
            return _text_response(self.forced_text_when_no_tools)
        if self.responses:
            return self.responses.pop(0)
        return _text_response("")


@dataclass
class _FakeTools:
    outputs: list[str]

    def __post_init__(self) -> None:
        self.calls = 0

    def execute(self, call: dict[str, Any], *, tools: list[Any] | None = None) -> str:
        _ = (call, tools)
        output = self.outputs[self.calls] if self.calls < len(self.outputs) else self.outputs[-1]
        self.calls += 1
        return output


class _FakeLLM:
    queued_responses: ClassVar[list[object]] = []
    queued_outputs: ClassVar[list[str]] = []
    forced_text_when_no_tools = "forced final answer"

    def __init__(self, model: str, api_key: str | None = None, api_base: str | None = None) -> None:
        _ = (api_key, api_base)
        provider, model_name = model.split(":", 1)
        self.provider = provider
        self.model = model_name
        self.chat = _FakeChat(
            responses=list(self.queued_responses),
            forced_text_when_no_tools=self.forced_text_when_no_tools,
        )
        self.tools = _FakeTools(outputs=list(self.queued_outputs))


def _capture_events(events: list[ToolEvent]):
    def _handler(event: ToolEvent) -> None:
        events.append(event)

    return _handler


def test_tool_result_payload_is_structured_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setattr("bub.agent.core.LLM", _FakeLLM)
    _FakeLLM.queued_responses = [
        _tool_call_response(name="fs.read", arguments='{"path":"calc.py"}'),
        _text_response("done"),
    ]
    _FakeLLM.queued_outputs = ["file-content"]
    _FakeLLM.forced_text_when_no_tools = "forced final answer"

    agent = Agent(context=Context(tmp_path), tools=[SimpleNamespace(name="fs.read")])
    events: list[ToolEvent] = []

    result = agent.respond([{"role": "user", "content": "check file"}], on_event=_capture_events(events))

    assert result == "done"
    tool_result_events = [event for event in events if event.kind == "tool_result"]
    assert len(tool_result_events) == 1

    payload_text = tool_result_events[0].payload["result"][0]["content"]
    payload = json.loads(payload_text)
    assert payload["tool"] == "fs.read"
    assert payload["category"] == "verification"
    assert payload["status"] == "ok"
    assert payload["repeat"] is False
    machine = payload["machine_readable"]
    assert machine["format"] == "text"
    assert machine["value"] == "file-content"
    assert payload["human_preview"] == "file-content"
    assert payload["signature"] == 'fs.read:{"path":"calc.py"}'


def test_agent_recovers_when_observations_are_stagnant(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setattr("bub.agent.core.LLM", _FakeLLM)
    _FakeLLM.queued_responses = [
        _tool_call_response(name="fs.read", arguments='{"path":"calc.py"}'),
        _tool_call_response(name="fs.read", arguments='{"path":"calc.py"}'),
    ]
    _FakeLLM.queued_outputs = ["same-output", "same-output"]
    _FakeLLM.forced_text_when_no_tools = "final answer without more tools"

    agent = Agent(context=Context(tmp_path), tools=[SimpleNamespace(name="fs.read")])
    events: list[ToolEvent] = []

    result = agent.respond([{"role": "user", "content": "fix and verify"}], on_event=_capture_events(events))

    assert result == "final answer without more tools"
    tool_result_events = [event for event in events if event.kind == "tool_result"]
    assert len(tool_result_events) == 2

    second_payload_text = tool_result_events[1].payload["result"][0]["content"]
    second_payload = json.loads(second_payload_text)
    assert second_payload["status"] == "stagnant"
    assert second_payload["repeat"] is True


def test_agent_does_not_hard_block_completion_without_verification_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setattr("bub.agent.core.LLM", _FakeLLM)
    _FakeLLM.queued_responses = [_text_response("completed")]
    _FakeLLM.queued_outputs = []
    _FakeLLM.forced_text_when_no_tools = "forced final answer"

    agent = Agent(context=Context(tmp_path), tools=[SimpleNamespace(name="fs.read")])

    result = agent.respond([{"role": "user", "content": "请验证完成结果后再回复完成"}])

    assert result == "completed"


def test_agent_allows_completion_with_verification_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setattr("bub.agent.core.LLM", _FakeLLM)
    _FakeLLM.queued_responses = [
        _tool_call_response(name="fs.read", arguments='{"path":"out.txt"}'),
        _text_response("verified completion"),
    ]
    _FakeLLM.queued_outputs = ["ok-content"]
    _FakeLLM.forced_text_when_no_tools = "forced final answer"

    agent = Agent(context=Context(tmp_path), tools=[SimpleNamespace(name="fs.read")])

    result = agent.respond([{"role": "user", "content": "please verify completion and then conclude"}])

    assert result == "verified completion"
