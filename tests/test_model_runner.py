from dataclasses import dataclass, field

from bub.core.model_runner import TOOL_CONTINUE_PROMPT, ModelRunner
from bub.core.router import AssistantRouteResult
from bub.skills.loader import SkillMetadata
from republic import ToolAutoResult


class FakeRouter:
    def __init__(self) -> None:
        self._calls = 0

    def route_assistant(self, raw: str) -> AssistantRouteResult:
        self._calls += 1
        if self._calls == 1:
            assert raw == "assistant-first"
            return AssistantRouteResult(visible_text="v1", next_prompt="<command>one</command>", exit_requested=False)
        assert raw == "assistant-second"
        return AssistantRouteResult(visible_text="v2", next_prompt="", exit_requested=False)


class SingleStepRouter:
    def route_assistant(self, raw: str) -> AssistantRouteResult:
        assert raw == "assistant-only"
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class AnySingleStepRouter:
    def route_assistant(self, raw: str) -> AssistantRouteResult:
        assert raw
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class FollowupRouter:
    def __init__(self, *, first: str, second: str) -> None:
        self._calls = 0
        self._first = first
        self._second = second

    def route_assistant(self, raw: str) -> AssistantRouteResult:
        self._calls += 1
        if self._calls == 1:
            assert raw == self._first
            return AssistantRouteResult(
                visible_text="", next_prompt="<command>followup</command>", exit_requested=False
            )
        assert raw == self._second
        return AssistantRouteResult(visible_text="done", next_prompt="", exit_requested=False)


class ToolFollowupRouter:
    def route_assistant(self, raw: str) -> AssistantRouteResult:
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


@dataclass
class FakeTapeImpl:
    outputs: list[ToolAutoResult]
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    def run_tools(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        tools: list[object],
    ) -> ToolAutoResult:
        self.calls.append((prompt, system_prompt, max_tokens))
        return self.outputs.pop(0)


@dataclass
class FakeTapeService:
    tape: FakeTapeImpl
    events: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def append_event(self, name: str, data: dict[str, object]) -> None:
        self.events.append((name, data))


def test_model_runner_follows_command_context_until_stop() -> None:
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
        skills=[],
        load_skill_body=lambda name: None,
        model="openrouter:test",
        max_steps=5,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="workspace",
    )

    result = runner.run("start")
    assert result.visible_text == "v1\n\nv2"
    assert result.steps == 2
    assert result.command_followups == 1
    assert result.error is None


def test_model_runner_continues_after_tool_execution() -> None:
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
        skills=[],
        load_skill_body=lambda name: None,
        model="openrouter:test",
        max_steps=3,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="workspace",
    )

    result = runner.run("create file")
    assert result.visible_text == "tool done"
    assert result.steps == 2
    assert result.command_followups == 1
    assert tape.tape.calls[1][0] == TOOL_CONTINUE_PROMPT


def test_model_runner_tool_followup_does_not_inline_tool_payload() -> None:
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
        skills=[],
        load_skill_body=lambda name: None,
        model="openrouter:test",
        max_steps=3,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="workspace",
    )

    runner.run("create file")
    followup_prompt = tape.tape.calls[1][0]
    assert followup_prompt == TOOL_CONTINUE_PROMPT


def test_model_runner_expands_skill_from_hint() -> None:
    tape = FakeTapeService(FakeTapeImpl(outputs=[ToolAutoResult.text_result("assistant-only")]))
    skill = SkillMetadata(
        name="friendly-python",
        description="style",
        location=__file__,  # type: ignore[arg-type]
        source="project",
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        skills=[skill],
        load_skill_body=lambda name: f"body for {name}",
        model="openrouter:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="",
    )

    runner.run("please follow $friendly-python")
    _, system_prompt, _ = tape.tape.calls[0]
    assert "<skill_details>" in system_prompt
    assert "friendly-python" in system_prompt


def test_model_runner_expands_skill_from_assistant_hint() -> None:
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
        source="project",
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=FollowupRouter(first="assistant mentions $friendly-python", second="assistant-second"),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
        tools=[],
        skills=[skill],
        load_skill_body=lambda name: f"body for {name}",
        model="openrouter:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="",
    )

    runner.run("no skill hint here")
    _, second_system_prompt, _ = tape.tape.calls[1]
    assert "<skill_details>" in second_system_prompt
    assert "friendly-python" in second_system_prompt


def test_model_runner_expands_tool_from_user_hint() -> None:
    tool_view = FakeToolView()
    tape = FakeTapeService(FakeTapeImpl(outputs=[ToolAutoResult.text_result("assistant-only")]))
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=AnySingleStepRouter(),  # type: ignore[arg-type]
        tool_view=tool_view,  # type: ignore[arg-type]
        tools=[],
        skills=[],
        load_skill_body=lambda name: None,
        model="openrouter:test",
        max_steps=1,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="",
    )

    runner.run("use $fs.read")
    _, first_system_prompt, _ = tape.tape.calls[0]
    assert "<tool_details>" in first_system_prompt
    assert '<tool name="fs.read"/>' in first_system_prompt


def test_model_runner_expands_tool_from_assistant_hint() -> None:
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
        skills=[],
        load_skill_body=lambda name: None,
        model="openrouter:test",
        max_steps=2,
        max_tokens=512,
        model_timeout_seconds=90,
        base_system_prompt="base",
        workspace_system_prompt="",
    )

    runner.run("no tool hint here")
    _, second_system_prompt, _ = tape.tape.calls[1]
    assert "<tool_details>" in second_system_prompt
    assert '<tool name="fs.read"/>' in second_system_prompt
