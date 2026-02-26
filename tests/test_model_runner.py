from dataclasses import dataclass, field
from typing import Any

import pytest
from republic import ToolAutoResult

from bub.core.model_runner import TOOL_CONTINUE_PROMPT, ModelRunner
from bub.core.router import AssistantRouteResult
from bub.skills.loader import SkillMetadata


class FakeRouter:
    def __init__(self) -> None:
        self._calls = 0

    async def route_assistant(self, raw: str) -> AssistantRouteResult:
        self._calls += 1
        if self._calls == 1:
            assert raw == "assistant-first"
            return AssistantRouteResult(visible_text="v1", next_prompt="<command>one</command>", exit_requested=False)
        assert raw == "assistant-second"
        return AssistantRouteResult(visible_text="v2", next_prompt="", exit_requested=False)


class SingleStepRouter:
    async def route_assistant(self, raw: str) -> AssistantRouteResult:
        assert raw == "assistant-only"
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class AnySingleStepRouter:
    async def route_assistant(self, raw: str) -> AssistantRouteResult:
        assert raw
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class FollowupRouter:
    def __init__(self, *, first: str, second: str) -> None:
        self._calls = 0
        self._first = first
        self._second = second

    async def route_assistant(self, raw: str) -> AssistantRouteResult:
        self._calls += 1
        if self._calls == 1:
            assert raw == self._first
            return AssistantRouteResult(
                visible_text="", next_prompt="<command>followup</command>", exit_requested=False
            )
        assert raw == self._second
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class ToolFollowupRouter:
    async def route_assistant(self, raw: str) -> AssistantRouteResult:
        assert raw == "assistant-after-tool"
        return AssistantRouteResult(visible_text="tool done", next_prompt="", exit_requested=False)


class FakeToolView:
    def __init__(self) -> None:
        self.expanded: set[str] = set()

    def compact_block(self) -> str:
        return "<tool_view/>"

    def expanded_block(self) -> str:
        if not self.expanded:
            return ""
        lines = ["<tool_details>"]
        for name in sorted(self.expanded):
            lines.append(f'  <tool name="{name}"/>')
        lines.append("</tool_details>")
        return "\n".join(lines)

    def note_hint(self, hint: str) -> bool:
        normalized = hint.casefold()
        if normalized == "fs.read":
            self.expanded.add("fs.read")
            return True
        return False


@dataclass(frozen=True)
class FakeStreamEvent:
    kind: str
    data: dict[str, Any]


@dataclass
class FakeAsyncStreamEvents:
    events: list[FakeStreamEvent]
    error: object | None = None

    def __aiter__(self):
        async def _iterator():
            for event in self.events:
                yield event

        return _iterator()


def _stream_from_tool_auto(output: ToolAutoResult) -> FakeAsyncStreamEvents:
    if output.kind == "text":
        text = output.text or ""
        return FakeAsyncStreamEvents(
            events=[
                FakeStreamEvent("text", {"delta": text}),
                FakeStreamEvent(
                    "final",
                    {
                        "text": text,
                        "tool_calls": [],
                        "tool_results": [],
                        "usage": None,
                        "ok": True,
                    },
                ),
            ]
        )

    if output.kind == "tools":
        events = [
            FakeStreamEvent("tool_call", {"index": idx, "call": call}) for idx, call in enumerate(output.tool_calls)
        ]
        events.extend([
            FakeStreamEvent("tool_result", {"index": idx, "result": result})
            for idx, result in enumerate(output.tool_results)
        ])
        events.append(
            FakeStreamEvent(
                "final",
                {
                    "text": None,
                    "tool_calls": output.tool_calls,
                    "tool_results": output.tool_results,
                    "usage": None,
                    "ok": True,
                },
            )
        )
        return FakeAsyncStreamEvents(events=events)

    error_kind = output.error.kind.value if output.error is not None else "unknown"
    error_message = output.error.message if output.error is not None else "unknown"
    return FakeAsyncStreamEvents(
        events=[
            FakeStreamEvent("error", {"kind": error_kind, "message": error_message}),
            FakeStreamEvent(
                "final",
                {
                    "text": None,
                    "tool_calls": output.tool_calls,
                    "tool_results": output.tool_results,
                    "usage": None,
                    "ok": False,
                },
            ),
        ]
    )


@dataclass
class FakeTapeImpl:
    outputs: list[ToolAutoResult | FakeAsyncStreamEvents]
    calls: list[tuple[str, str, int]] = field(default_factory=list)
    parallel_tool_calls_values: list[bool | None] = field(default_factory=list)

    async def stream_events_async(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        tools: list[object],
        parallel_tool_calls: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> FakeAsyncStreamEvents:
        self.calls.append((prompt, system_prompt, max_tokens))
        self.parallel_tool_calls_values.append(parallel_tool_calls)
        output = self.outputs.pop(0)
        if isinstance(output, FakeAsyncStreamEvents):
            return output
        return _stream_from_tool_auto(output)


@dataclass
class FakeTapeService:
    tape: FakeTapeImpl
    events: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def append_event(self, name: str, data: dict[str, object]) -> None:
        self.events.append((name, data))


@pytest.mark.asyncio
async def test_model_runner_follows_command_context_until_stop() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                ToolAutoResult.text_result("assistant-first"),
                ToolAutoResult.text_result("assistant-second"),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=FakeRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        model="openrouter:test",
        max_steps=5,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "workspace",
    )

    result = await runner.run("start")
    assert result.visible_text == "v1\n\nv2"
    assert result.steps == 2
    assert result.command_followups == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_model_runner_continues_after_tool_execution() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                ToolAutoResult.tools_result(
                    tool_calls=[{"function": {"name": "fs.write", "arguments": '{"path":"tmp.txt","content":"hi"}'}}],
                    tool_results=["ok"],
                ),
                ToolAutoResult.text_result("assistant-after-tool"),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=ToolFollowupRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        model="openrouter:test",
        max_steps=3,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "workspace",
    )

    result = await runner.run("create file")
    assert result.visible_text == "tool done"
    assert result.steps == 2
    assert result.command_followups == 1
    assert tape.tape.calls[1][0] == TOOL_CONTINUE_PROMPT


@pytest.mark.asyncio
async def test_model_runner_tool_followup_does_not_inline_tool_payload() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                ToolAutoResult.tools_result(
                    tool_calls=[
                        {
                            "function": {
                                "name": 'fs.write"unsafe',
                                "arguments": '{"path":"tmp/<unsafe>.txt","content":"x & y"}',
                            }
                        }
                    ],
                    tool_results=['ok <done> & "quoted"'],
                ),
                ToolAutoResult.text_result("assistant-after-tool"),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=ToolFollowupRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        model="openrouter:test",
        max_steps=3,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "workspace",
    )

    await runner.run("create file")
    followup_prompt = tape.tape.calls[1][0]
    assert followup_prompt == TOOL_CONTINUE_PROMPT


@pytest.mark.asyncio
async def test_model_runner_expands_skill_from_hint() -> None:
    tape = FakeTapeService(FakeTapeImpl(outputs=[ToolAutoResult.text_result("assistant-only")]))
    skill = SkillMetadata(
        name="friendly-python",
        description="style",
        location=__file__,  # type: ignore[arg-type]
        body="content",
        source="project",
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [skill],
        model="openrouter:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    await runner.run("please follow $friendly-python")
    _, system_prompt, _ = tape.tape.calls[0]
    assert "<basic_skills>" in system_prompt
    assert "friendly-python" in system_prompt


@pytest.mark.asyncio
async def test_model_runner_expands_skill_from_assistant_hint() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                ToolAutoResult.text_result("assistant mentions $friendly-python"),
                ToolAutoResult.text_result("assistant-second"),
            ]
        )
    )
    skill = SkillMetadata(
        name="friendly-python",
        description="style",
        location=__file__,  # type: ignore[arg-type]
        body="content",
        source="project",
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=FollowupRouter(first="assistant mentions $friendly-python", second="assistant-second"),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [skill],
        model="openrouter:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    await runner.run("no skill hint here")
    _, second_system_prompt, _ = tape.tape.calls[1]
    assert "<basic_skills>" in second_system_prompt
    assert "friendly-python" in second_system_prompt


@pytest.mark.asyncio
async def test_model_runner_expands_tool_from_user_hint() -> None:
    tool_view = FakeToolView()
    tape = FakeTapeService(FakeTapeImpl(outputs=[ToolAutoResult.text_result("assistant-only")]))
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=tool_view,  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        model="openrouter:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    await runner.run("use $fs.read")
    _, first_system_prompt, _ = tape.tape.calls[0]
    assert "<tool_details>" in first_system_prompt
    assert '<tool name="fs.read"/>' in first_system_prompt


@pytest.mark.asyncio
async def test_model_runner_expands_tool_from_assistant_hint() -> None:
    tool_view = FakeToolView()
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                ToolAutoResult.text_result("assistant mentions $fs.read"),
                ToolAutoResult.text_result("assistant-second"),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=FollowupRouter(first="assistant mentions $fs.read", second="assistant-second"),  # type: ignore[arg-type]
        tool_view=tool_view,  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        model="openrouter:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    await runner.run("no tool hint here")
    _, second_system_prompt, _ = tape.tape.calls[1]
    assert "<tool_details>" in second_system_prompt
    assert '<tool name="fs.read"/>' in second_system_prompt


@pytest.mark.asyncio
async def test_model_runner_refreshes_skills_from_provider_between_runs() -> None:
    skill = SkillMetadata(
        name="friendly-python",
        description="style",
        location=__file__,  # type: ignore[arg-type]
        body="content",
        source="project",
    )
    all_skills: list[SkillMetadata] = []

    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[ToolAutoResult.text_result("assistant-only"), ToolAutoResult.text_result("assistant-only")]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: list(all_skills),
        model="openrouter:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )
    await runner.run("first run")
    _, first_system_prompt, _ = tape.tape.calls[0]
    assert "friendly-python" not in first_system_prompt

    all_skills.append(skill)
    await runner.run("second run")
    _, second_system_prompt, _ = tape.tape.calls[1]
    assert "<basic_skills>" in second_system_prompt
    assert "friendly-python" in second_system_prompt


@pytest.mark.asyncio
async def test_model_runner_reports_stream_error_event() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                FakeAsyncStreamEvents(
                    events=[
                        FakeStreamEvent(
                            "error",
                            {
                                "kind": "provider",
                                "message": "non-streaming is not supported",
                            },
                        ),
                        FakeStreamEvent(
                            "final",
                            {
                                "text": None,
                                "tool_calls": [],
                                "tool_results": [],
                                "usage": None,
                                "ok": False,
                            },
                        ),
                    ]
                )
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        load_skill_body=lambda name: None,
        model="anthropic:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    result = await runner.run("start")
    assert result.error == "provider: non-streaming is not supported"
    assert tape.tape.parallel_tool_calls_values == [False]


@pytest.mark.asyncio
async def test_model_runner_does_not_send_parallel_tool_calls_to_non_anthropic() -> None:
    tape = FakeTapeService(FakeTapeImpl(outputs=[ToolAutoResult.text_result("assistant-only")]))
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        load_skill_body=lambda name: None,
        model="gemini:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    result = await runner.run("start")
    assert result.error is None
    assert tape.tape.parallel_tool_calls_values == [None]


@pytest.mark.asyncio
async def test_model_runner_prefers_stream_error_over_tool_followup() -> None:
    tape = FakeTapeService(
        FakeTapeImpl(
            outputs=[
                FakeAsyncStreamEvents(
                    events=[
                        FakeStreamEvent(
                            "error",
                            {
                                "kind": "tool",
                                "message": "No runnable tools are available.",
                            },
                        ),
                        FakeStreamEvent(
                            "final",
                            {
                                "text": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "fs.read", "arguments": '{"path":"a.txt"}'},
                                    }
                                ],
                                "tool_results": [],
                                "usage": None,
                                "ok": False,
                            },
                        ),
                    ]
                ),
                ToolAutoResult.text_result("assistant-only"),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        list_skills=lambda: [],
        load_skill_body=lambda name: None,
        model="anthropic:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        get_workspace_system_prompt=lambda: "",
    )

    result = await runner.run("start")
    assert result.error == "tool: No runnable tools are available."
    assert len(tape.tape.calls) == 1
