"""Republic-driven runtime engine to process prompts."""

from __future__ import annotations

import asyncio
import inspect
import re
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

from pluggy import PluginManager
from republic import LLM, AsyncTapeStore, Tool, ToolAutoResult, ToolContext
from republic.tape import InMemoryTapeStore, Tape, TapeStore

from bub.builtin.context import default_tape_context
from bub.builtin.settings import RuntimeSettings
from bub.builtin.tape import TapeService
from bub.skills import discover_skills, render_skills_prompt
from bub.tools import model_tools, render_tools_prompt
from bub.types import State

CONTINUE_PROMPT = "Continue the task."
DEFAULT_BUB_HEADERS = {"HTTP-Referer": "https://bub.build/", "X-Title": "Bub"}
HINT_RE = re.compile(r"\$([A-Za-z0-9_.-]+)")


class RuntimeEngine:
    """Runtime engine with command compatibility and Republic model driving."""

    def __init__(self, plugins_manager: PluginManager) -> None:
        self.settings = _load_runtime_settings()
        tape_store = plugins_manager.hook.provide_tape_store()
        if tape_store is None:
            tape_store = InMemoryTapeStore()
        self._llm = _build_llm(self.settings, tape_store)
        self._pm = plugins_manager
        self.tapes = TapeService(self._llm, self.settings.home / "tapes")

    @cached_property
    def tools(self) -> list[Tool]:
        tools: dict[str, Tool] = {}
        for provided in reversed(self._pm.hook.provide_tools()):
            tools.update((tool.name, tool) for tool in provided)
        return list(tools.values())

    @cached_property
    def model_tools(self) -> list[Tool]:
        return model_tools(self.tools)

    async def run(self, *, session_id: str, prompt: str, state: State) -> str:
        stripped = prompt.strip()
        if not stripped:
            return "error: empty prompt"
        tape = self.tapes.session_tape(session_id)
        await self.tapes.ensure_bootstrap_anchor(tape.name)
        tape.context.state.update(state)
        if stripped.startswith(","):
            return await self._run_command(tape=tape, line=stripped)
        return await self._run_model(tape=tape, prompt=stripped)

    async def _run_command(self, tape: Tape, *, line: str) -> str:
        line = line[1:].strip()
        if not line:
            raise ValueError("empty command")

        name, arg_tokens = _parse_internal_command(line)
        start = time.monotonic()
        context = ToolContext(tape=tape.name, run_id="run_command", state=tape.context.state)
        tools = {tool.name: tool for tool in self.tools}
        output = ""
        status = "ok"
        try:
            if name not in tools:
                output = await tools["bash"].run(context=context, cmd=line)
            else:
                args = _parse_args(arg_tokens)
                if tools[name].context:
                    args.kwargs["context"] = context
                output = tools[name].run(*args.positional, **args.kwargs)
                if inspect.isawaitable(output):
                    output = await output
        except Exception as exc:
            status = "error"
            output = f"{exc!s}"
            raise
        else:
            return output if isinstance(output, str) else str(output)
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            output_text = output if isinstance(output, str) else str(output)

            event_payload = {
                "raw": line,
                "name": name,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "output": output_text,
                "date": datetime.now(UTC).isoformat(),
            }
            await self.tapes.append_event(tape.name, "command", event_payload)

    async def _run_model(self, *, tape: Tape, prompt: str) -> str:
        next_prompt = prompt

        for step in range(1, self.settings.max_steps + 1):
            start = time.monotonic()
            await self.tapes.append_event(tape.name, "loop.step.start", {"step": step, "prompt": next_prompt})
            try:
                output = await self._run_tools_once(tape=tape, prompt=next_prompt)
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                await self.tapes.append_event(
                    tape.name,
                    "loop.step",
                    {
                        "step": step,
                        "elapsed_ms": elapsed_ms,
                        "status": "error",
                        "error": f"{exc!s}",
                        "date": datetime.now(UTC).isoformat(),
                    },
                )
                raise

            outcome = _resolve_tool_auto_result(output)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if outcome.kind == "text":
                await self.tapes.append_event(
                    tape.name,
                    "loop.step",
                    {
                        "step": step,
                        "elapsed_ms": elapsed_ms,
                        "status": "ok",
                        "date": datetime.now(UTC).isoformat(),
                    },
                )
                return outcome.text
            if outcome.kind == "continue":
                if "context" in tape.context.state:
                    next_prompt = f"{CONTINUE_PROMPT} [context: {tape.context.state['context']}]"
                else:
                    next_prompt = CONTINUE_PROMPT
                await self.tapes.append_event(
                    tape.name,
                    "loop.step",
                    {
                        "step": step,
                        "elapsed_ms": elapsed_ms,
                        "status": "continue",
                        "date": datetime.now(UTC).isoformat(),
                    },
                )
                continue
            await self.tapes.append_event(
                tape.name,
                "loop.step",
                {
                    "step": step,
                    "elapsed_ms": elapsed_ms,
                    "status": "error",
                    "error": outcome.error,
                    "date": datetime.now(UTC).isoformat(),
                },
            )
            raise RuntimeError(outcome.error)

        raise RuntimeError(f"max_steps_reached={self.settings.max_steps}")

    def _load_skills_prompt(self, prompt: str, workspace: Path) -> str:
        skill_index = {skill.name: skill for skill in discover_skills(workspace)}
        expanded_skills = set(HINT_RE.findall(prompt)) & set(skill_index.keys())
        return render_skills_prompt(list(skill_index.values()), expanded_skills=expanded_skills)

    async def _run_tools_once(self, *, tape: Tape, prompt: str) -> ToolAutoResult:
        async with asyncio.timeout(self.settings.model_timeout_seconds):
            return await tape.run_tools_async(
                prompt=prompt,
                system_prompt=self._system_prompt(prompt, state=tape.context.state),
                max_tokens=self.settings.max_tokens,
                tools=self.model_tools,
                extra_headers=DEFAULT_BUB_HEADERS,
            )

    def _system_prompt(self, prompt: str, state: State) -> str:
        blocks: list[str] = []
        for result in reversed(self._pm.hook.system_prompt(prompt=prompt, state=state)):
            if result:
                blocks.append(result)
        tools_prompt = render_tools_prompt(self.tools)
        if tools_prompt:
            blocks.append(tools_prompt)
        workspace = workspace_from_state(state)
        if skills_prompt := self._load_skills_prompt(prompt, workspace):
            blocks.append(skills_prompt)
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class _ToolAutoOutcome:
    kind: str
    text: str = ""
    error: str = ""


def _resolve_tool_auto_result(output: ToolAutoResult) -> _ToolAutoOutcome:
    if output.kind == "text":
        return _ToolAutoOutcome(kind="text", text=output.text or "")
    if output.kind == "tools" or output.tool_calls or output.tool_results:
        return _ToolAutoOutcome(kind="continue")
    if output.error is None:
        return _ToolAutoOutcome(kind="error", error="tool_auto_error: unknown")
    error_kind = getattr(output.error.kind, "value", str(output.error.kind))
    return _ToolAutoOutcome(kind="error", error=f"{error_kind}: {output.error.message}")


def _build_llm(settings: RuntimeSettings, tape_store: TapeStore | AsyncTapeStore) -> LLM:
    return LLM(
        settings.model,
        api_key=settings.api_key,
        api_base=settings.api_base,
        tape_store=tape_store,
        context=default_tape_context(),
    )


def _load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings()


@dataclass(frozen=True)
class Args:
    positional: list[str]
    kwargs: dict[str, Any]


def _parse_internal_command(line: str) -> tuple[str, list[str]]:
    body = line.strip()
    words = shlex.split(body)
    if not words:
        return "", []
    return words[0], words[1:]


def _parse_args(args_tokens: list[str]) -> Args:
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    first_kwarg = False
    for token in args_tokens:
        if "=" in token:
            key, value = token.split("=", 1)
            kwargs[key] = value
            first_kwarg = True
        elif first_kwarg:
            raise ValueError(f"positional argument '{token}' cannot appear after keyword arguments")
        else:
            positional.append(token)
    return Args(positional=positional, kwargs=kwargs)


def workspace_from_state(state: State) -> Path:
    raw = state.get("_runtime_workspace")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()
