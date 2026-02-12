"""Forward-only agent loop."""

from __future__ import annotations

import asyncio
from contextvars import copy_context
from dataclasses import dataclass
from functools import partial

from bub.core.model_runner import ModelRunner, ModelTurnResult
from bub.core.router import InputRouter
from bub.tape.service import TapeService


@dataclass(frozen=True)
class LoopResult:
    """Loop output for one input turn."""

    immediate_output: str
    assistant_output: str
    exit_requested: bool
    steps: int
    error: str | None = None
    reaction: str | None = None


class AgentLoop:
    """Deterministic single-session loop built on an endless tape."""

    def __init__(self, *, router: InputRouter, model_runner: ModelRunner, tape: TapeService) -> None:
        self._router = router
        self._model_runner = model_runner
        self._tape = tape

    async def handle_input(self, raw: str) -> LoopResult:
        with self._tape.fork_tape():
            ctx = copy_context()
            route = await asyncio.get_event_loop().run_in_executor(None, ctx.run, partial(self._router.route_user, raw))
            if route.exit_requested:
                return LoopResult(
                    immediate_output=route.immediate_output,
                    assistant_output="",
                    exit_requested=True,
                    steps=0,
                    error=None,
                )

            if not route.enter_model:
                return LoopResult(
                    immediate_output=route.immediate_output,
                    assistant_output="",
                    exit_requested=False,
                    steps=0,
                    error=None,
                )

            model_result = await self._model_runner.run(route.model_prompt)
            self._record_result(model_result)
            return LoopResult(
                immediate_output=route.immediate_output,
                assistant_output=model_result.visible_text,
                exit_requested=model_result.exit_requested,
                steps=model_result.steps,
                error=model_result.error,
                reaction=model_result.reaction,
            )

    def _record_result(self, result: ModelTurnResult) -> None:
        self._tape.append_event(
            "loop.result",
            {
                "steps": result.steps,
                "followups": result.command_followups,
                "exit_requested": result.exit_requested,
                "error": result.error,
            },
        )
