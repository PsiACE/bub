"""Model turn runner."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from loguru import logger
from republic import Tool, ToolAutoResult

from bub.core.router import AssistantRouteResult, InputRouter
from bub.skills.loader import SkillMetadata
from bub.skills.view import render_compact_skills
from bub.tape.service import TapeService
from bub.tools.progressive import ProgressiveToolView
from bub.tools.view import render_tool_prompt_block

HINT_RE = re.compile(r"\$([A-Za-z0-9_.-]+)")
TOOL_CONTINUE_PROMPT = "Continue the task."


@dataclass(frozen=True)
class ModelTurnResult:
    """Result of one model turn loop."""

    visible_text: str
    exit_requested: bool
    steps: int
    error: str | None = None
    command_followups: int = 0


@dataclass
class _PromptState:
    prompt: str
    step: int = 0
    followups: int = 0
    visible_parts: list[str] = field(default_factory=list)
    error: str | None = None
    exit_requested: bool = False


class ModelRunner:
    """Runs assistant loop over tape with command-aware follow-up handling."""

    def __init__(
        self,
        *,
        tape: TapeService,
        router: InputRouter,
        tool_view: ProgressiveToolView,
        tools: list[Tool],
        skills: list[SkillMetadata],
        load_skill_body: Callable[[str], str | None],
        model: str,
        max_steps: int,
        max_tokens: int,
        model_timeout_seconds: int | None,
        base_system_prompt: str,
        workspace_system_prompt: str,
    ) -> None:
        self._tape = tape
        self._router = router
        self._tool_view = tool_view
        self._tools = tools
        self._skills = skills
        self._load_skill_body = load_skill_body
        self._model = model
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._model_timeout_seconds = model_timeout_seconds
        self._base_system_prompt = base_system_prompt.strip()
        self._workspace_system_prompt = workspace_system_prompt.strip()
        self._expanded_skills: dict[str, str] = {}
        self._skill_index = {skill.name.casefold(): skill for skill in skills}

    async def run(self, prompt: str) -> ModelTurnResult:
        state = _PromptState(prompt=prompt)
        self._activate_hints(prompt)

        while state.step < self._max_steps and not state.exit_requested:
            state.step += 1
            logger.info("model.runner.step step={} model={}", state.step, self._model)
            self._tape.append_event(
                "loop.step.start",
                {
                    "step": state.step,
                    "model": self._model,
                },
            )
            response = await self._chat(state.prompt)
            if response.error is not None:
                state.error = response.error
                self._tape.append_event(
                    "loop.step.error",
                    {
                        "step": state.step,
                        "error": response.error,
                    },
                )
                break

            if response.followup_prompt:
                self._tape.append_event(
                    "loop.step.finish",
                    {
                        "step": state.step,
                        "visible_text": False,
                        "followup": True,
                        "exit_requested": False,
                    },
                )
                state.prompt = response.followup_prompt
                state.followups += 1
                continue

            assistant_text = response.text
            if not assistant_text.strip():
                self._tape.append_event("loop.step.empty", {"step": state.step})
                break

            self._activate_hints(assistant_text)
            route = self._router.route_assistant(assistant_text)
            self._consume_route(state, route)
            if not route.next_prompt:
                break
            state.prompt = route.next_prompt
            state.followups += 1

        if state.step >= self._max_steps and not state.error:
            state.error = f"max_steps_reached={self._max_steps}"
            self._tape.append_event("loop.max_steps", {"max_steps": self._max_steps})

        return ModelTurnResult(
            visible_text="\n\n".join(part for part in state.visible_parts if part).strip(),
            exit_requested=state.exit_requested,
            steps=state.step,
            error=state.error,
            command_followups=state.followups,
        )

    def _consume_route(self, state: _PromptState, route: AssistantRouteResult) -> None:
        if route.visible_text:
            state.visible_parts.append(route.visible_text)
        if route.exit_requested:
            state.exit_requested = True
        self._tape.append_event(
            "loop.step.finish",
            {
                "step": state.step,
                "visible_text": bool(route.visible_text),
                "followup": bool(route.next_prompt),
                "exit_requested": route.exit_requested,
            },
        )

    async def _chat(self, prompt: str) -> _ChatResult:
        system_prompt = self._render_system_prompt()
        try:
            async with asyncio.timeout(self._model_timeout_seconds):
                output = await self._tape.tape.run_tools_async(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=self._max_tokens,
                    tools=self._tools,
                )
                return _ChatResult.from_tool_auto(output)
        except TimeoutError:
            return _ChatResult(
                text="",
                error=f"model_timeout: no response within {self._model_timeout_seconds}s",
            )
        except Exception as exc:
            logger.exception("model.call.error")
            return _ChatResult(text="", error=f"model_call_error: {exc!s}")

    def _render_system_prompt(self) -> str:
        blocks: list[str] = []
        if self._base_system_prompt:
            blocks.append(self._base_system_prompt)
        if self._workspace_system_prompt:
            blocks.append(self._workspace_system_prompt)
        memory_context = self._tape.memory.get_context()
        if memory_context:
            blocks.append(f"<memory>\n{memory_context}\n</memory>")
        blocks.append(_runtime_contract())
        blocks.append(render_tool_prompt_block(self._tool_view))

        compact_skills = render_compact_skills(self._skills)
        if compact_skills:
            blocks.append(compact_skills)

        if self._expanded_skills:
            lines = ["<skill_details>"]
            for name, body in sorted(self._expanded_skills.items()):
                lines.append(f'  <skill name="{name}">')
                for line in body.splitlines():
                    lines.append(f"    {line}")
                lines.append("  </skill>")
            lines.append("</skill_details>")
            blocks.append("\n".join(lines))
        return "\n\n".join(block for block in blocks if block.strip())

    def _activate_hints(self, text: str) -> None:
        for match in HINT_RE.finditer(text):
            hint = match.group(1)
            self._tool_view.note_hint(hint)

            skill = self._skill_index.get(hint.casefold())
            if skill is None:
                continue
            if skill.name in self._expanded_skills:
                continue
            body = self._load_skill_body(skill.name)
            if body:
                self._expanded_skills[skill.name] = body


@dataclass(frozen=True)
class _ChatResult:
    text: str
    error: str | None = None
    followup_prompt: str | None = None

    @classmethod
    def from_tool_auto(cls, output: ToolAutoResult) -> _ChatResult:
        if output.kind == "text":
            return cls(text=output.text or "")
        if output.kind == "tools":
            return cls(text="", followup_prompt=TOOL_CONTINUE_PROMPT)

        if output.tool_calls or output.tool_results:
            return cls(text="", followup_prompt=TOOL_CONTINUE_PROMPT)

        if output.error is None:
            return cls(text="", error="tool_auto_error: unknown")
        return cls(text="", error=f"{output.error.kind.value}: {output.error.message}")


def _runtime_contract() -> str:
    from datetime import UTC, datetime

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC (%A)")
    return (
        "<runtime_contract>\n"
        f"current_time: {now}\n"
        "1) Use function calling tools for all actions (file ops, shell, web, tape, skills).\n"
        "2) Do not emit comma-prefixed commands in normal flow; use tool calls instead.\n"
        "3) If a compatibility fallback is required, runtime can still parse comma commands.\n"
        "4) Never emit '<command ...>' blocks yourself; those are runtime-generated.\n"
        "5) When enough evidence is collected, return plain natural language answer.\n"
        "6) Use '$name' hints to request detail expansion for tools/skills when needed.\n"
        "7) When the user shares a preference, project context, or important fact, "
        "use `memory_save` to persist it. Use `memory_daily` to log work progress.\n"
        "</runtime_contract>"
    )
