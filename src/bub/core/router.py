"""Routing and command execution."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bub.core.commands import ParsedArgs, parse_command_words, parse_internal_command, parse_kv_arguments
from bub.core.types import DetectedCommand
from bub.tape.service import TapeService
from bub.tools.progressive import ProgressiveToolView
from bub.tools.registry import ToolRegistry


@dataclass(frozen=True)
class CommandExecutionResult:
    """Result of one command execution."""

    command: str
    name: str
    status: str
    output: str
    elapsed_ms: int

    def block(self) -> str:
        return f'<command name="{self.name}" status="{self.status}">\n{self.output}\n</command>'


@dataclass(frozen=True)
class UserRouteResult:
    """Routing outcome for user input."""

    enter_model: bool
    model_prompt: str
    immediate_output: str
    exit_requested: bool


@dataclass(frozen=True)
class AssistantRouteResult:
    """Routing outcome for assistant output."""

    visible_text: str
    next_prompt: str
    exit_requested: bool


class InputRouter:
    """Command-aware router used by both user and model outputs."""

    def __init__(
        self,
        registry: ToolRegistry,
        tool_view: ProgressiveToolView,
        tape: TapeService,
        workspace: Path,
    ) -> None:
        self._registry = registry
        self._tool_view = tool_view
        self._tape = tape
        self._workspace = workspace

    def route_user(self, raw: str) -> UserRouteResult:
        stripped = raw.strip()
        if not stripped:
            return UserRouteResult(enter_model=False, model_prompt="", immediate_output="", exit_requested=False)

        command = self._detect_user_command(stripped)
        if command is None:
            return UserRouteResult(enter_model=True, model_prompt=stripped, immediate_output="", exit_requested=False)

        result = self._execute_command(command, origin="human")
        if result.status == "ok" and result.name != "bash":
            if result.name == "quit" and result.output == "exit":
                return UserRouteResult(
                    enter_model=False,
                    model_prompt="",
                    immediate_output="",
                    exit_requested=True,
                )
            return UserRouteResult(
                enter_model=False,
                model_prompt="",
                immediate_output=result.output,
                exit_requested=False,
            )

        if result.status == "ok" and result.name == "bash":
            return UserRouteResult(
                enter_model=False,
                model_prompt="",
                immediate_output=result.output,
                exit_requested=False,
            )

        # Failed command falls back to model with command block context.
        return UserRouteResult(
            enter_model=True,
            model_prompt=result.block(),
            immediate_output=result.output,
            exit_requested=False,
        )

    def _detect_user_command(self, stripped: str) -> DetectedCommand | None:
        return self._parse_comma_prefixed_command(stripped)

    def route_assistant(self, raw: str) -> AssistantRouteResult:
        visible_lines: list[str] = []
        command_blocks: list[str] = []
        exit_requested = False
        in_fence = False
        pending_command_lines: list[str] = []
        pending_source_lines: list[str] = []

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("```"):
                if in_fence:
                    exit_requested = (
                        self._flush_pending_assistant_command(
                            pending_command_lines=pending_command_lines,
                            pending_source_lines=pending_source_lines,
                            visible_lines=visible_lines,
                            command_blocks=command_blocks,
                        )
                        or exit_requested
                    )
                in_fence = not in_fence
                continue

            if in_fence:
                shell_candidate = self._parse_comma_prefixed_command(stripped)
                if shell_candidate is not None and shell_candidate.kind == "shell":
                    exit_requested = (
                        self._flush_pending_assistant_command(
                            pending_command_lines=pending_command_lines,
                            pending_source_lines=pending_source_lines,
                            visible_lines=visible_lines,
                            command_blocks=command_blocks,
                        )
                        or exit_requested
                    )
                    pending_command_lines.append(shell_candidate.raw)
                    pending_source_lines.append(line)
                    continue
                if pending_command_lines:
                    pending_command_lines.append(line)
                    pending_source_lines.append(line)
                    continue
                visible_lines.append(line)
                continue

            command = self._detect_assistant_command(stripped)
            if command is None:
                visible_lines.append(line)
                continue

            exit_requested = self._execute_assistant_command(command, command_blocks) or exit_requested

        exit_requested = (
            self._flush_pending_assistant_command(
                pending_command_lines=pending_command_lines,
                pending_source_lines=pending_source_lines,
                visible_lines=visible_lines,
                command_blocks=command_blocks,
            )
            or exit_requested
        )
        visible_text = "\n".join(visible_lines).strip()
        if command_blocks:
            # Hide execution-phase chatter and keep only post-execution assistant answers.
            visible_text = ""
        next_prompt = "\n".join(command_blocks).strip()
        return AssistantRouteResult(
            visible_text=visible_text,
            next_prompt=next_prompt,
            exit_requested=exit_requested,
        )

    def _execute_assistant_command(self, command: DetectedCommand, command_blocks: list[str]) -> bool:
        result = self._execute_command(command, origin="assistant")
        command_blocks.append(result.block())
        return result.name == "quit" and result.status == "ok" and result.output == "exit"

    def _flush_pending_assistant_command(
        self,
        *,
        pending_command_lines: list[str],
        pending_source_lines: list[str],
        visible_lines: list[str],
        command_blocks: list[str],
    ) -> bool:
        if not pending_command_lines:
            return False

        command_text = "\n".join(pending_command_lines).strip()
        words = parse_command_words(command_text)
        command = (
            DetectedCommand(kind="shell", raw=command_text, name=words[0], args_tokens=words[1:]) if words else None
        )
        pending_command_lines.clear()
        source_lines = list(pending_source_lines)
        pending_source_lines.clear()

        if command is None:
            visible_lines.extend(source_lines)
            return False
        return self._execute_assistant_command(command, command_blocks)

    def _detect_assistant_command(self, stripped: str) -> DetectedCommand | None:
        return self._parse_comma_prefixed_command(stripped)

    def _parse_comma_prefixed_command(self, stripped: str) -> DetectedCommand | None:
        if not stripped.startswith(","):
            return None
        body = stripped[1:].lstrip()
        if not body:
            return None
        name, args_tokens = parse_internal_command(stripped)
        if name:
            resolved = self._resolve_internal_name(name)
            if self._registry.has(resolved):
                return DetectedCommand(kind="internal", raw=stripped, name=name, args_tokens=args_tokens)

        words = parse_command_words(body)
        if not words:
            return None
        return DetectedCommand(kind="shell", raw=body, name=words[0], args_tokens=words[1:])

    def _execute_command(self, command: DetectedCommand, *, origin: str) -> CommandExecutionResult:
        start = time.time()

        if command.kind == "shell":
            return self._execute_shell(command, origin=origin, start=start)
        return self._execute_internal(command, origin=origin, start=start)

    def _execute_shell(self, command: DetectedCommand, *, origin: str, start: float) -> CommandExecutionResult:
        elapsed_ms: int
        try:
            output = self._registry.execute(
                "bash",
                kwargs={
                    "cmd": command.raw,
                    "cwd": str(self._workspace),
                },
            )
            status = "ok"
            text = str(output)
        except Exception as exc:
            status = "error"
            text = f"{exc!s}"

        elapsed_ms = int((time.time() - start) * 1000)
        self._record_command(command=command, status=status, output=text, elapsed_ms=elapsed_ms, origin=origin)
        return CommandExecutionResult(
            command=command.raw,
            name="bash",
            status=status,
            output=text,
            elapsed_ms=elapsed_ms,
        )

    def _execute_internal(self, command: DetectedCommand, *, origin: str, start: float) -> CommandExecutionResult:
        name = self._resolve_internal_name(command.name)
        parsed_args = parse_kv_arguments(command.args_tokens)

        if name == "tool.describe" and parsed_args.positional and "name" not in parsed_args.kwargs:
            parsed_args.kwargs["name"] = parsed_args.positional[0]

        if name == "handoff":
            self._inject_default_handoff_name(parsed_args)

        if self._registry.has(name) is False:
            elapsed_ms = int((time.time() - start) * 1000)
            text = f"unknown internal command: {command.name}"
            self._record_command(command=command, status="error", output=text, elapsed_ms=elapsed_ms, origin=origin)
            return CommandExecutionResult(
                command=command.raw,
                name=name,
                status="error",
                output=text,
                elapsed_ms=elapsed_ms,
            )

        try:
            output = self._registry.execute(name, kwargs=dict(parsed_args.kwargs))
            status = "ok"
            text = str(output)
            if name == "tool.describe":
                described = parsed_args.kwargs.get("name")
                if isinstance(described, str):
                    self._tool_view.note_selected(described)
            elif name not in {"help", "tools"}:
                self._tool_view.note_selected(name)
        except Exception as exc:
            status = "error"
            text = f"{exc!s}"

        elapsed_ms = int((time.time() - start) * 1000)
        self._record_command(command=command, status=status, output=text, elapsed_ms=elapsed_ms, origin=origin)
        return CommandExecutionResult(
            command=command.raw,
            name=name,
            status=status,
            output=text,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _resolve_internal_name(name: str) -> str:
        aliases = {
            "tool": "tool.describe",
            "tape": "tape.info",
            "skill": "skills.describe",
        }
        return aliases.get(name, name)

    @staticmethod
    def _inject_default_handoff_name(parsed_args: ParsedArgs) -> None:
        if "name" in parsed_args.kwargs:
            return
        if parsed_args.positional:
            parsed_args.kwargs["name"] = parsed_args.positional[0]
        else:
            parsed_args.kwargs["name"] = "handoff"

    def _record_command(
        self,
        *,
        command: DetectedCommand,
        status: str,
        output: str,
        elapsed_ms: int,
        origin: str,
    ) -> None:
        self._tape.append_event(
            "command",
            {
                "origin": origin,
                "kind": command.kind,
                "raw": command.raw,
                "name": command.name,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "output": output,
            },
        )

    def render_failure_context(self, result: CommandExecutionResult) -> str:
        return result.block()

    @staticmethod
    def to_json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False)
