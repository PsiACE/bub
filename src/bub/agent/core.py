"""Core agent implementation for Bub."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from republic import LLM, Tool

from ..errors import ModelNotConfiguredError
from .context import Context

MODEL_NOT_CONFIGURED_ERROR = "Model not configured. Set BUB_MODEL (e.g., 'openai:gpt-4o-mini')."
STAGNATION_RECOVERY_PROMPT = (
    "Tool observations are repeating with no new information. "
    "Do not call any tool. Provide a final direct answer based on current context."
)
HUMAN_PREVIEW_MAX_LEN = 240
HUMAN_PREVIEW_TRUNCATE_LEN = 237
VERIFICATION_TOOL_NAMES = {
    "fs_read",
    "fs_grep",
    "fs_glob",
    "tape_search",
    "tape_info",
    "tape_anchors",
    "status",
    "web_fetch",
    "web_search",
}
BASH_VERIFICATION_TOKENS = (
    "pytest",
    "unittest",
    "go test",
    "cargo test",
    "just test",
    "make test",
    "npm test",
    "pnpm test",
    "uv run pytest",
    "python -m pytest",
    "python3 -m pytest",
    "python -m unittest",
    "python3 -m unittest",
    "ls",
    "cat ",
    "grep ",
    "find ",
    "wc ",
    "head ",
    "tail ",
    "stat ",
)


@dataclass(frozen=True)
class ToolEvent:
    kind: str
    payload: dict[str, Any]


class Agent:
    """LLM wrapper that returns a single assistant response per turn."""

    def __init__(
        self,
        context: Context,
        model: str | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
    ) -> None:
        self._context = context
        settings = context.settings
        resolved_model = model or settings.model
        if not resolved_model:
            raise ModelNotConfiguredError(MODEL_NOT_CONFIGURED_ERROR)
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens
        self._system_prompt = system_prompt if system_prompt is not None else (settings.system_prompt or "")
        self._llm = LLM(
            model=resolved_model,
            api_key=settings.api_key,
            api_base=settings.api_base,
        )
        self._tools: list[Tool] = tools or []

    @property
    def model(self) -> str:
        """Return the resolved provider:model string for display."""
        return f"{self._llm.provider}:{self._llm.model}"

    @property
    def tool_names(self) -> list[str]:
        """Return available tool names."""
        return [tool.name for tool in self._tools]

    @property
    def context(self) -> Context:
        """Return the agent context."""
        return self._context

    def respond(
        self,
        messages: list[dict[str, Any]],
        on_event: Callable[[ToolEvent], None] | None = None,
    ) -> str:
        """Run a tool-aware response and return assistant text."""
        if self._system_prompt:
            messages = [{"role": "system", "content": self._system_prompt}, *messages]

        observation_fingerprints: dict[str, str] = {}
        while True:
            response = self._llm.chat.raw(
                messages=messages,
                tools=self._tools,
                max_tokens=self._max_tokens,
            )
            tool_calls = self._extract_tool_calls(response)
            text = self._extract_text(response)
            if tool_calls:
                messages.append(self._build_assistant_message(text, tool_calls))
                if on_event:
                    on_event(ToolEvent("tool_call", {"calls": tool_calls}))
                tool_messages, is_stagnant = self._execute_tools(
                    tool_calls,
                    observation_fingerprints,
                )
                if on_event:
                    on_event(ToolEvent("tool_result", {"result": tool_messages}))
                messages.extend(tool_messages)
                if is_stagnant:
                    return self._recover_from_stagnation(messages)
                continue

            return text or ""

    def _execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
        observation_fingerprints: dict[str, str],
    ) -> tuple[list[dict[str, Any]], bool]:
        tool_messages: list[dict[str, Any]] = []
        has_new_observation = False
        for idx, call in enumerate(tool_calls):
            call_id = call.get("id") or str(idx)
            signature = _tool_signature(call)
            try:
                result = self._llm.tools.execute(call, tools=self._tools) or ""
            except Exception as exc:
                # Tool implementations may raise arbitrary exceptions; convert to tool error payload.
                result = f"error: {exc!s}"

            raw_output = str(result)
            fingerprint = _tool_result_fingerprint(raw_output)
            is_repeat = observation_fingerprints.get(signature) == fingerprint
            if not is_repeat:
                has_new_observation = True
            observation_fingerprints[signature] = fingerprint

            tool_name = _tool_name(call)
            category = "verification" if _is_verification_tool_call(call) else "operation"
            status = _tool_status(raw_output, is_repeat)

            payload = {
                "tool": tool_name,
                "signature": signature,
                "category": category,
                "status": status,
                "repeat": is_repeat,
                "machine_readable": _machine_readable(raw_output),
                "human_preview": _human_preview(raw_output),
            }
            if is_repeat:
                payload["note"] = "No new information from repeated tool call."
            tool_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(payload, ensure_ascii=False),
            })
        is_stagnant = bool(tool_calls) and not has_new_observation
        return tool_messages, is_stagnant

    def _recover_from_stagnation(self, messages: list[dict[str, Any]]) -> str:
        final_messages = [
            *messages,
            {"role": "system", "content": STAGNATION_RECOVERY_PROMPT},
        ]
        response = self._llm.chat.raw(
            messages=final_messages,
            tools=[],
            max_tokens=self._max_tokens,
        )
        text = self._extract_text(response).strip()
        if text:
            return text
        return "Unable to make further progress with tools. Please refine the request."

    def _extract_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        return getattr(message, "content", "") or ""

    def _extract_tool_calls(self, response: Any) -> list[dict[str, Any]]:
        choices = getattr(response, "choices", None)
        if not choices:
            return []
        message = getattr(choices[0], "message", None)
        if message is None:
            return []
        tool_calls = getattr(message, "tool_calls", None) or []
        calls: list[dict[str, Any]] = []
        for idx, tool_call in enumerate(tool_calls):
            function = getattr(tool_call, "function", None)
            if function is None:
                continue
            entry: dict[str, Any] = {
                "function": {
                    "name": getattr(function, "name", ""),
                    "arguments": getattr(function, "arguments", ""),
                }
            }
            call_id = getattr(tool_call, "id", None) or str(idx)
            entry["id"] = call_id
            call_type = getattr(tool_call, "type", None)
            if call_type:
                entry["type"] = call_type
            calls.append(entry)
        return calls

    def _build_assistant_message(self, text: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        content: str | None = text if text else None
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}


def _tool_name(call: dict[str, Any]) -> str:
    function = call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str):
            return name
    return "-"


def _tool_signature(call: dict[str, Any]) -> str:
    function = call.get("function")
    if not isinstance(function, dict):
        return "-"
    name = function.get("name")
    arguments = function.get("arguments")
    normalized_name = name if isinstance(name, str) else "-"
    normalized_arguments = _normalize_arguments(arguments)
    return f"{normalized_name}:{normalized_arguments}"


def _normalize_arguments(arguments: object) -> str:
    if isinstance(arguments, dict):
        return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if not isinstance(arguments, str):
        try:
            return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except TypeError:
            return str(arguments)
    raw = arguments.strip()
    if not raw:
        return "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _tool_result_fingerprint(raw_output: str) -> str:
    normalized = raw_output.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _tool_status(raw_output: str, is_repeat: bool) -> str:
    if is_repeat:
        return "stagnant"
    if raw_output.strip().startswith("error:"):
        return "error"
    return "ok"


def _machine_readable(raw_output: str) -> dict[str, Any]:
    stripped = raw_output.strip()
    if not stripped:
        return {"format": "text", "value": ""}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"format": "text", "value": raw_output}
    return {"format": "json", "value": parsed}


def _human_preview(raw_output: str) -> str:
    preview = raw_output.strip().replace("\n", " | ")
    if not preview:
        return "(empty)"
    if len(preview) > HUMAN_PREVIEW_MAX_LEN:
        return preview[:HUMAN_PREVIEW_TRUNCATE_LEN] + "..."
    return preview


def _is_verification_tool_call(call: dict[str, Any]) -> bool:
    name = _tool_name(call)
    if name in VERIFICATION_TOOL_NAMES:
        return True
    if name != "bash":
        return False
    cmd = _bash_command(call).lower()
    return any(token in cmd for token in BASH_VERIFICATION_TOKENS)


def _bash_command(call: dict[str, Any]) -> str:
    function = call.get("function")
    if not isinstance(function, dict):
        return ""
    arguments = function.get("arguments")
    normalized = _normalize_arguments(arguments)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if not isinstance(payload, dict):
        return normalized
    cmd = payload.get("cmd")
    return cmd if isinstance(cmd, str) else normalized
