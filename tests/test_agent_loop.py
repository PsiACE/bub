from dataclasses import dataclass

from bub.core.agent_loop import AgentLoop
from bub.core.model_runner import ModelTurnResult
from bub.core.router import UserRouteResult


@dataclass
class FakeRouter:
    route: UserRouteResult

    def route_user(self, _raw: str) -> UserRouteResult:
        return self.route


@dataclass
class FakeRunner:
    result: ModelTurnResult

    def run(self, _prompt: str) -> ModelTurnResult:
        return self.result


class FakeTape:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def append_event(self, name: str, data: dict[str, object]) -> None:
        self.events.append((name, data))


def test_loop_short_circuit_without_model() -> None:
    loop = AgentLoop(
        router=FakeRouter(
            UserRouteResult(
                enter_model=False,
                model_prompt="",
                immediate_output="ok",
                exit_requested=False,
            )
        ),  # type: ignore[arg-type]
        model_runner=FakeRunner(ModelTurnResult("", False, 0)),  # type: ignore[arg-type]
        tape=FakeTape(),  # type: ignore[arg-type]
    )
    result = loop.handle_input(",help")
    assert result.immediate_output == "ok"
    assert result.assistant_output == ""


def test_loop_runs_model_when_router_requests() -> None:
    loop = AgentLoop(
        router=FakeRouter(
            UserRouteResult(
                enter_model=True,
                model_prompt="context",
                immediate_output="cmd error",
                exit_requested=False,
            )
        ),  # type: ignore[arg-type]
        model_runner=FakeRunner(ModelTurnResult("answer", False, 2)),  # type: ignore[arg-type]
        tape=FakeTape(),  # type: ignore[arg-type]
    )
    result = loop.handle_input("bad cmd")
    assert result.immediate_output == "cmd error"
    assert result.assistant_output == "answer"
    assert result.steps == 2
