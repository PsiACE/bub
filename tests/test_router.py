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
    for text in (",echo hi", ", echo hi", ",   echo hi"):
        result = router.route_user(text)
        assert result.enter_model is False
        assert result.immediate_output == "ok from bash"


def test_user_shell_failure_falls_back_to_model() -> None:
    router = _build_router(bash_error=True)
    for text in (",echo hi", ", echo hi", ",   echo hi"):
        result = router.route_user(text)
        assert result.enter_model is True
        assert "<command name=\"bash\" status=\"error\">" in result.model_prompt


def test_user_natural_language_starting_with_command_word_goes_to_model() -> None:
    router = _build_router()
    result = router.route_user("write another python file buggy , just run , then wait ten second then fix")
    assert result.enter_model is True
    assert result.immediate_output == ""
    assert result.model_prompt.startswith("write another")


def test_user_plain_shell_like_text_without_prefix_goes_to_model() -> None:
    router = _build_router()
    result = router.route_user("echo hi")
    assert result.enter_model is True
    assert result.immediate_output == ""
    assert result.model_prompt == "echo hi"


def test_user_non_line_start_comma_text_goes_to_model() -> None:
    router = _build_router()
    result = router.route_user("please run ,echo hi")
    assert result.enter_model is True
    assert result.immediate_output == ""
    assert result.model_prompt == "please run ,echo hi"


def test_user_dollar_prefix_goes_to_model_as_plain_text() -> None:
    router = _build_router()
    result = router.route_user("$echo hi")
    assert result.enter_model is True
    assert result.immediate_output == ""
    assert result.model_prompt == "$echo hi"


def test_assistant_plain_shell_text_is_not_executed() -> None:
    router = _build_router()
    result = router.route_assistant("will run command\necho hi")
    assert result.visible_text == "will run command\necho hi"
    assert result.next_prompt == ""


def test_assistant_non_line_start_comma_text_is_not_executed() -> None:
    router = _build_router()
    result = router.route_assistant("please run ,echo hi")
    assert result.visible_text == "please run ,echo hi"
    assert result.next_prompt == ""


def test_assistant_legacy_dollar_prefix_is_visible_text() -> None:
    router = _build_router()
    result = router.route_assistant("$ echo hi")
    assert result.visible_text == "$ echo hi"
    assert result.next_prompt == ""


def test_internal_quit_sets_exit_requested() -> None:
    router = _build_router()
    result = router.route_user(",quit")
    assert result.exit_requested is True


def test_assistant_comma_prefixed_shell_command_is_executed() -> None:
    router = _build_router()
    for line in (",echo hi", ", echo hi", ",   echo hi"):
        result = router.route_assistant(f"create file\n{line}")
        assert result.visible_text == ""
        assert "<command name=\"bash\" status=\"ok\">" in result.next_prompt


def test_assistant_internal_command_with_comma_is_executed() -> None:
    router = _build_router()
    result = router.route_assistant("show help\n,help")
    assert result.visible_text == ""
    assert "<command name=\"help\" status=\"ok\">" in result.next_prompt


def test_assistant_fenced_multiline_comma_command_is_executed() -> None:
    router = _build_router()
    for line in (",echo first", ", echo first", ",   echo first"):
        result = router.route_assistant(f"I will run this:\n```\n{line}\necho second\n```")
        assert result.visible_text == ""
        assert "<command name=\"bash\" status=\"ok\">" in result.next_prompt


def test_assistant_fenced_plain_text_is_not_executed() -> None:
    router = _build_router()
    result = router.route_assistant("```\necho hi\n```")
    assert result.visible_text == "echo hi"
    assert result.next_prompt == ""
