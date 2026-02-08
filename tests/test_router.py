from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field
from republic import tool_from_model

from bub.core.router import InputRouter
from bub.tools.progressive import ProgressiveToolView
from bub.tools.registry import ToolDescriptor, ToolRegistry


class BashInput(BaseModel):
    cmd: str = Field(...)
    cwd: str | None = Field(default=None)


class EmptyInput(BaseModel):
    pass


@dataclass
class FakeTape:
    events: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def append_event(self, name: str, data: dict[str, object]) -> None:
        self.events.append((name, data))


def _build_router(*, bash_error: bool = False) -> InputRouter:
    registry = ToolRegistry()

    def run_bash(params: BashInput) -> str:
        if bash_error:
            raise RuntimeError
        return "ok from bash"

    def command_help(_params: EmptyInput) -> str:
        return "help text"

    def quit_command(_params: EmptyInput) -> str:
        return "exit"

    registry.register(
        ToolDescriptor(
            name="bash",
            short_description="Run shell command",
            detail="bash detail",
            tool=tool_from_model(BashInput, run_bash, name="bash"),
        )
    )
    registry.register(
        ToolDescriptor(
            name="help",
            short_description="help",
            detail="help detail",
            tool=tool_from_model(EmptyInput, command_help, name="help"),
        )
    )
    registry.register(
        ToolDescriptor(
            name="quit",
            short_description="quit",
            detail="quit detail",
            tool=tool_from_model(EmptyInput, quit_command, name="quit"),
        )
    )

    view = ProgressiveToolView(registry)
    return InputRouter(registry, view, FakeTape(), Path.cwd())


def test_user_internal_command_short_circuits_model() -> None:
    router = _build_router()
    result = router.route_user(",help")
    assert result.enter_model is False
    assert result.immediate_output == "help text"


def test_user_shell_success_short_circuits_model() -> None:
    router = _build_router()
    result = router.route_user("echo hi")
    assert result.enter_model is False
    assert result.immediate_output == "ok from bash"


def test_user_shell_failure_falls_back_to_model() -> None:
    router = _build_router(bash_error=True)
    result = router.route_user("echo hi")
    assert result.enter_model is True
    assert "<command name=\"bash\" status=\"error\">" in result.model_prompt


def test_assistant_text_and_command_are_split() -> None:
    router = _build_router()
    result = router.route_assistant("will run command\necho hi")
    assert result.visible_text == "will run command"
    assert "<command name=\"bash\" status=\"ok\">" in result.next_prompt


def test_internal_quit_sets_exit_requested() -> None:
    router = _build_router()
    result = router.route_user(",quit")
    assert result.exit_requested is True
