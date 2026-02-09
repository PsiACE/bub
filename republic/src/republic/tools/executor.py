"""Tool execution helpers for Republic."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from republic.core.errors import ErrorKind
from republic.core.results import ErrorPayload, ToolExecution
from republic.tools.context import ToolContext
from republic.tools.schema import Tool, ToolInput, normalize_tools


class ToolExecutor:
    """Execute tool calls with predictable validation and serialization."""

    def __init__(self) -> None:
        self._skip = object()

    def execute(
        self,
        response: list[dict[str, Any]] | dict[str, Any] | str,
        tools: ToolInput = None,
        *,
        context: ToolContext | None = None,
    ) -> ToolExecution:
        tool_calls, error = self._normalize_response(response)
        if error is not None:
            return ToolExecution(tool_calls=[], tool_results=[], error=error)

        tool_map, tool_error = self._build_tool_map(tools)
        if tool_error is not None:
            return ToolExecution(tool_calls=tool_calls, tool_results=[], error=tool_error)
        if not tool_map:
            if tool_calls:
                return ToolExecution(
                    tool_calls=tool_calls,
                    tool_results=[],
                    error=ErrorPayload(ErrorKind.TOOL, "No runnable tools are available."),
                )
            return ToolExecution(tool_calls=[], tool_results=[], error=None)

        results: list[Any] = []
        for tool_response in tool_calls:
            outcome, outcome_error = self._handle_tool_response(tool_response, tool_map, context)
            if outcome_error is not None:
                return ToolExecution(tool_calls=tool_calls, tool_results=results, error=outcome_error)
            if outcome is self._skip:
                continue
            results.append(outcome)

        return ToolExecution(tool_calls=tool_calls, tool_results=results, error=None)

    def _handle_tool_response(
        self,
        tool_response: Any,
        tool_map: dict[str, Tool],
        context: ToolContext | None,
    ) -> tuple[Any, ErrorPayload | None]:
        if not isinstance(tool_response, dict):
            return self._skip, None
        tool_name = tool_response.get("function", {}).get("name")
        if not tool_name:
            return self._skip, ErrorPayload(ErrorKind.INVALID_INPUT, "Tool call is missing name.")
        tool_obj = tool_map.get(tool_name)
        if tool_obj is None:
            return self._skip, ErrorPayload(ErrorKind.TOOL, f"Unknown tool name: {tool_name}.")
        tool_args = tool_response.get("function", {}).get("arguments", {})
        tool_args, error = self._normalize_tool_args(tool_name, tool_args)
        if error is not None:
            return self._skip, error
        try:
            if tool_obj.context:
                if context is None:
                    return self._skip, ErrorPayload(
                        ErrorKind.INVALID_INPUT,
                        f"Tool '{tool_name}' requires context but none was provided.",
                    )
                return tool_obj.run(context=context, **tool_args), None
            return tool_obj.run(**tool_args), None
        except ValidationError as exc:
            return self._skip, ErrorPayload(
                ErrorKind.INVALID_INPUT,
                f"Tool '{tool_name}' argument validation failed.",
                details={"errors": exc.errors()},
            )
        except Exception as exc:
            return self._skip, ErrorPayload(
                ErrorKind.TOOL,
                f"Tool '{tool_name}' execution failed.",
                details={"error": repr(exc)},
            )

    def _normalize_response(
        self,
        response: list[dict[str, Any]] | dict[str, Any] | str,
    ) -> tuple[list[dict[str, Any]], ErrorPayload | None]:
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError as exc:
                return [], ErrorPayload(
                    ErrorKind.INVALID_INPUT,
                    "Tool response is not a valid JSON string.",
                    details={"error": str(exc)},
                )
        if isinstance(response, dict):
            response = [response]
        if not isinstance(response, list):
            return [], ErrorPayload(ErrorKind.INVALID_INPUT, "Tool response must be a list of objects.")
        return response, None

    def _build_tool_map(self, tools: ToolInput) -> tuple[dict[str, Tool], ErrorPayload | None]:
        if tools is None:
            return {}, ErrorPayload(ErrorKind.INVALID_INPUT, "No tools provided.")
        try:
            toolset = normalize_tools(tools)
        except (ValueError, TypeError) as exc:
            return {}, ErrorPayload(ErrorKind.INVALID_INPUT, str(exc))

        return {tool_obj.name: tool_obj for tool_obj in toolset.runnable if tool_obj.name}, None

    def _normalize_tool_args(self, tool_name: str, tool_args: Any) -> tuple[dict[str, Any], ErrorPayload | None]:
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError:
                return {}, ErrorPayload(
                    ErrorKind.INVALID_INPUT,
                    f"Tool '{tool_name}' arguments are not valid JSON.",
                )
        if isinstance(tool_args, dict):
            return dict(tool_args), None
        return {}, ErrorPayload(
            ErrorKind.INVALID_INPUT,
            f"Tool '{tool_name}' arguments must be an object.",
        )
