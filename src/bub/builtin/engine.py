"""Republic-driven runtime battery used by runtime skill."""

from __future__ import annotations

import asyncio
import inspect
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path

from pluggy import PluginManager
from republic import LLM, AsyncTapeStore, Tool, ToolAutoResult, ToolContext
from republic.tape import InMemoryTapeStore, Tape, TapeStore

from bub.builtin.settings import RuntimeSettings
from bub.builtin.tape import TapeService
from bub.types import State

CONTINUE_PROMPT = "Continue the task."
DEFAULT_BUB_HEADERS = {"HTTP-Referer": "https://bub.build/", "X-Title": "Bub"}


class RuntimeEngine:
    """Runtime engine with command compatibility and Republic model driving."""

    def __init__(self, plugins_manager: PluginManager) -> None:
        self.settings = _load_runtime_settings()
        tape_store = plugins_manager.hook.provide_tape_store()
        if tape_store is None:
            tape_store = InMemoryTapeStore()
        self._llm = _build_llm(self.settings, tape_store)
        self._pm = plugins_manager
        self._tools: list[Tool] | None = None
        self.tapes = TapeService(self._llm, Path.home() / ".bub" / "tapes")

    def _load_tools(self) -> list[Tool]:
        tools: dict[str, Tool] = {}
        for provided in reversed(self._pm.hook.provide_tools()):
            if isinstance(provided, dict):
                tools.update(provided)
        return list(tools.values())

    @cached_property
    def tools(self) -> list[Tool]:
        if self._tools is None:
            self._tools = self._load_tools()
        return self._tools

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
        raw_body = line[1:].strip()
        if not raw_body:
            return "error: empty command"

        name, arg_tokens = _parse_internal_command(line)
        start = time.monotonic()
        context = ToolContext(tape=tape.name, run_id="run_command", state=tape.context.state)
        tools = {tool.name: tool for tool in self.tools}
        try:
            if name not in tools:
                output = await tools["bash"].run(context=context, cmd=line)
            else:
                args = _parse_args(arg_tokens)
                output = tools[name].run(*args.positional, context=context, **args.kwargs)
                if inspect.isawaitable(output):
                    output = await output
            status = "ok"
        except Exception as exc:
            status = "error"
            output = f"{exc!s}"
        elapsed_ms = int((time.monotonic() - start) * 1000)

        event_payload = {
            "raw": line,
            "name": name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "output": output,
            "date": datetime.now(UTC).isoformat(),
        }
        await self.tapes.append_event(tape.name, "command", event_payload)
        if status == "error":
            return f"error: {output}"
        return output

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
                return f"error: {exc!s}"

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
            return f"error: {outcome.error}"

        return f"error: max_steps_reached={self.settings.max_steps}"

    async def _run_tools_once(self, *, tape: Tape, prompt: str) -> ToolAutoResult:
        async with asyncio.timeout(self.settings.timeout_seconds):
            return await tape.run_tools_async(
                prompt=prompt,
                system_prompt=self._system_prompt(state=tape.context.state),
                max_tokens=self.settings.max_tokens,
                tools=self.tools,
                extra_headers=DEFAULT_BUB_HEADERS,
            )

    def _system_prompt(self, state: State) -> str:
        blocks = []
        for prompt in reversed(self._pm.hook.system_prompt(state=state)):
            blocks.append(prompt)
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
    )


def _load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings()


@dataclass(frozen=True)
class Args:
    positional: list[str]
    kwargs: dict[str, str]


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
