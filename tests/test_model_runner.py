from dataclasses import dataclass, field

from republic import StructuredOutput

from bub.core.model_runner import ModelRunner
from bub.core.router import AssistantRouteResult
from bub.skills.loader import SkillMetadata


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


class FakeToolView:
    def compact_block(self) -> str:
        return "<tool_view/>"

    def expanded_block(self) -> str:
        return ""


@dataclass
class FakeTapeImpl:
    outputs: list[StructuredOutput]
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    def chat(self, *, prompt: str, system_prompt: str, max_tokens: int) -> StructuredOutput:
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
                StructuredOutput("assistant-first", error=None),
                StructuredOutput("assistant-second", error=None),
            ]
        )
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=FakeRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
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


def test_model_runner_expands_skill_from_hint() -> None:
    tape = FakeTapeService(FakeTapeImpl(outputs=[StructuredOutput("assistant-only", error=None)]))
    skill = SkillMetadata(
        name="friendly-python",
        description="style",
        location=__file__,  # type: ignore[arg-type]
        source="project",
    )
    runner = ModelRunner(
        tape=tape,  # type: ignore[arg-type]
        router=SingleStepRouter(),  # type: ignore[arg-type]
        tool_view=FakeToolView(),  # type: ignore[arg-type]
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
