"""Session routing and command execution for Bub."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from republic import Tool

from ..agent.core import Agent
from ..tape import LANE_CONTROL, META_LANE, META_VIEW, CommandRecord, TapeService
from .router import (
    ActionOutcome,
    ActionSegment,
    AssistantResult,
    RouteResult,
    Segment,
    TextSegment,
    build_tool_kwargs,
    format_action_block,
    format_shell_args,
    is_debug_outcome,
    is_done_outcome,
    is_quit_outcome,
    normalize_command_output,
    parse_segments,
    segments_are_only_text,
    strip_leading_dollar,
)


@dataclass
class SegmentRun:
    output_parts: list[str]
    action_blocks: list[str]
    text_present: bool
    had_error: bool
    ran_command: bool
    exit_requested: bool
    done_requested: bool


class Session:
    """Route and execute user/assistant command segments."""

    def __init__(
        self,
        tools: list[Tool],
        tape: TapeService,
        workspace_path: Path,
        agent: Agent,
        *,
        bash_tool: Tool,
    ) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._tool_names = set(self._tools.keys())
        self._tape = tape
        self._workspace_path = workspace_path
        self._bash_tool = bash_tool
        self._agent = agent

    @property
    def agent(self) -> Agent:
        return self._agent

    @property
    def tape(self) -> TapeService:
        return self._tape

    def handle_input(self, raw: str, *, origin: str = "human") -> RouteResult:
        self._tape.record_user_message(raw)
        result = self.route(raw, origin=origin)
        if result.enter_agent and result.agent_input:
            self._tape.record_context_message(result.agent_input)
        return result

    def route(self, raw: str, *, origin: str = "human") -> RouteResult:
        segments = parse_segments(raw, self._tool_names)
        if not segments:
            return RouteResult("", False, False, False)

        leading_text = strip_leading_dollar(raw)
        if leading_text is not None and segments_are_only_text(segments):
            if not leading_text.strip():
                return RouteResult("", False, False, False)
            return RouteResult(leading_text, True, False, False)

        run = self._run_segments(segments, origin=origin, include_actions=True)
        if not run.text_present and run.ran_command:
            if run.had_error:
                agent_input = "".join(run.action_blocks).strip()
                return RouteResult(agent_input, True, run.exit_requested, run.done_requested)
            return RouteResult("", False, run.exit_requested, run.done_requested)

        agent_input = "".join(run.output_parts).strip()
        return RouteResult(agent_input, True, run.exit_requested, run.done_requested)

    def interpret_assistant(self, raw: str) -> AssistantResult:
        segments = parse_segments(raw, self._tool_names)
        if not segments:
            return AssistantResult("", False, False, "")

        run = self._run_segments(segments, origin="assistant", include_actions=False)
        followup_input = "".join(run.action_blocks).strip()
        visible_text = "".join(run.output_parts).strip()
        return AssistantResult(
            followup_input=followup_input,
            exit_requested=run.exit_requested,
            done_requested=run.done_requested,
            visible_text=visible_text,
        )

    def agent_respond(self, on_event=None) -> str:
        messages = self._tape.context_messages()
        return self._agent.respond(messages, on_event=on_event)

    def _run_segments(
        self,
        segments: list[Segment],
        *,
        origin: str,
        include_actions: bool,
    ) -> SegmentRun:
        output_parts: list[str] = []
        action_blocks: list[str] = []
        text_present = False
        exit_requested = False
        done_requested = False
        had_error = False
        ran_command = False

        for segment in segments:
            if isinstance(segment, TextSegment):
                output_parts.append(segment.text)
                if segment.text.strip():
                    text_present = True
                continue

            result = self._execute(segment, origin=origin)
            ran_command = True
            action_block = format_action_block(result)
            action_blocks.append(action_block)
            if result.status != "ok":
                had_error = True
            if is_quit_outcome(result):
                exit_requested = True
                break
            if is_debug_outcome(result):
                continue
            if is_done_outcome(result):
                done_requested = True
                break
            if include_actions:
                output_parts.append(action_block)

        return SegmentRun(
            output_parts=output_parts,
            action_blocks=action_blocks,
            text_present=text_present,
            had_error=had_error,
            ran_command=ran_command,
            exit_requested=exit_requested,
            done_requested=done_requested,
        )

    def _execute(self, segment: ActionSegment, *, origin: str) -> ActionOutcome:
        if segment.kind == "tool":
            return self._execute_tool(segment, origin)
        return self._execute_shell(segment, origin)

    def _execute_tool(self, segment: ActionSegment, origin: str) -> ActionOutcome:
        tool = self._tools.get(segment.name)
        if tool is None:
            return self._error_outcome(segment, "unknown command", origin)

        start = time.time()
        kwargs = build_tool_kwargs(segment)
        try:
            output = tool.run(**kwargs)
        except Exception as exc:
            # Tool adapters can raise non-uniform exceptions; keep session loop resilient.
            return self._error_outcome(segment, f"execution failed: {exc!s}", origin)

        elapsed = int((time.time() - start) * 1000)
        ok, message = normalize_command_output(output)
        if not ok:
            return self._error_outcome(segment, message, origin, elapsed_ms=elapsed)
        return self._success_outcome(segment, message, elapsed, origin)

    def _execute_shell(self, segment: ActionSegment, origin: str) -> ActionOutcome:
        args = [segment.name, *segment.args]
        start = time.time()
        cmd = format_shell_args(args)
        try:
            output = self._bash_tool.run(cmd=cmd, cwd=str(self._workspace_path))
        except Exception as exc:
            # Shell tool is an external boundary; convert failures into command outcomes.
            return self._error_outcome(segment, f"execution failed: {exc!s}", origin)

        elapsed = int((time.time() - start) * 1000)
        ok, message = normalize_command_output(output)
        if not ok:
            return self._error_outcome(segment, message, origin, elapsed_ms=elapsed)
        return self._success_outcome(segment, message, elapsed, origin)

    def _success_outcome(
        self,
        segment: ActionSegment,
        output: str,
        elapsed_ms: int,
        origin: str,
    ) -> ActionOutcome:
        outcome = ActionOutcome(
            name=segment.name,
            status="ok",
            stdout=output,
            stderr="",
            exit_code=0,
            elapsed_ms=elapsed_ms,
            intent=segment.raw,
            origin=origin,
        )
        self._record(outcome)
        return outcome

    def _error_outcome(
        self,
        segment: ActionSegment,
        message: str,
        origin: str,
        *,
        elapsed_ms: int = 0,
    ) -> ActionOutcome:
        outcome = ActionOutcome(
            name=segment.name,
            status="error",
            stdout="",
            stderr=message,
            exit_code=1,
            elapsed_ms=elapsed_ms,
            intent=segment.raw,
            origin=origin,
        )
        self._record(outcome)
        return outcome

    def _record(self, outcome: ActionOutcome) -> None:
        meta: dict | None = None
        if outcome.name in {"debug", "done"}:
            meta = {META_LANE: LANE_CONTROL, META_VIEW: False}
        record = CommandRecord(
            name=outcome.name,
            intent=outcome.intent,
            status=outcome.status,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            exit_code=outcome.exit_code,
            elapsed_ms=outcome.elapsed_ms,
            origin=outcome.origin,
        )
        self._tape.record_command(record, meta=meta)
