"""Structured text helpers for Republic."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Any

from pydantic import BaseModel, ValidationError

from republic.core.errors import ErrorKind
from republic.core.results import ErrorPayload, StructuredOutput
from republic.tape.context import TapeContext
from republic.tools.schema import schema_from_model


class _DecisionOutput(BaseModel):
    value: bool


class _ClassifyDecision(BaseModel):
    label: str


class TextClient:
    """Structured helpers built on chat tool calls."""

    def __init__(self, chat) -> None:
        self._chat = chat

    @staticmethod
    def _build_if_prompt(input_text: str, question: str) -> str:
        return dedent(
            f"""
            Here is an input:
            <input>
            {input_text.strip()}
            </input>

            And a question:
            <question>
            {question.strip()}
            </question>

            Answer by calling the tool with a boolean `value`.
            """
        ).strip()

    @staticmethod
    def _build_classify_prompt(input_text: str, choices_str: str) -> str:
        return dedent(
            f"""
            You are given this input:
            <input>
            {input_text.strip()}
            </input>

            And the following choices:
            <choices>
            {choices_str}
            </choices>

            Answer by calling the tool with `label` set to one of the choices.
            """
        ).strip()

    @staticmethod
    def _normalize_choices(choices: list[str]) -> tuple[list[str], ErrorPayload | None]:
        if not choices:
            return [], ErrorPayload(ErrorKind.INVALID_INPUT, "choices must not be empty.")
        normalized = [choice.strip() for choice in choices]
        return normalized, None

    def if_(
        self,
        input_text: str,
        question: str,
        *,
        tape: str | None = None,
        context: TapeContext | None = None,
    ) -> StructuredOutput:
        prompt = self._build_if_prompt(input_text, question)
        tool_schema = schema_from_model(_DecisionOutput, name="if_decision", description="Return a boolean.")
        response = self._chat.tool_calls(prompt=prompt, tools=[tool_schema], tape=tape, context=context)
        if response.error is not None:
            return StructuredOutput(None, response.error)
        return self._parse_tool_call(response.value, _DecisionOutput, field="value")

    async def if_async(
        self,
        input_text: str,
        question: str,
        *,
        tape: str | None = None,
        context: TapeContext | None = None,
    ) -> StructuredOutput:
        prompt = self._build_if_prompt(input_text, question)
        tool_schema = schema_from_model(_DecisionOutput, name="if_decision", description="Return a boolean.")
        response = await self._chat.tool_calls_async(prompt=prompt, tools=[tool_schema], tape=tape, context=context)
        if response.error is not None:
            return StructuredOutput(None, response.error)
        return self._parse_tool_call(response.value, _DecisionOutput, field="value")

    def classify(
        self,
        input_text: str,
        choices: list[str],
        *,
        tape: str | None = None,
        context: TapeContext | None = None,
    ) -> StructuredOutput:
        normalized, error = self._normalize_choices(choices)
        if error is not None:
            return StructuredOutput(None, error)
        choices_str = ", ".join(normalized)
        prompt = self._build_classify_prompt(input_text, choices_str)
        tool_schema = schema_from_model(_ClassifyDecision, name="classify_decision", description="Return one label.")
        response = self._chat.tool_calls(prompt=prompt, tools=[tool_schema], tape=tape, context=context)
        if response.error is not None:
            return StructuredOutput(None, response.error)

        parsed = self._parse_tool_call(response.value, _ClassifyDecision, field="label")
        if parsed.error is not None:
            return parsed
        label = parsed.value
        if label not in normalized:
            return StructuredOutput(
                None,
                ErrorPayload(
                    ErrorKind.INVALID_INPUT,
                    "classification label is not in the allowed choices.",
                    details={"label": label, "choices": normalized},
                ),
            )
        return StructuredOutput(label, None)

    async def classify_async(
        self,
        input_text: str,
        choices: list[str],
        *,
        tape: str | None = None,
        context: TapeContext | None = None,
    ) -> StructuredOutput:
        normalized, error = self._normalize_choices(choices)
        if error is not None:
            return StructuredOutput(None, error)
        choices_str = ", ".join(normalized)
        prompt = self._build_classify_prompt(input_text, choices_str)
        tool_schema = schema_from_model(_ClassifyDecision, name="classify_decision", description="Return one label.")
        response = await self._chat.tool_calls_async(prompt=prompt, tools=[tool_schema], tape=tape, context=context)
        if response.error is not None:
            return StructuredOutput(None, response.error)

        parsed = self._parse_tool_call(response.value, _ClassifyDecision, field="label")
        if parsed.error is not None:
            return parsed
        label = parsed.value
        if label not in normalized:
            return StructuredOutput(
                None,
                ErrorPayload(
                    ErrorKind.INVALID_INPUT,
                    "classification label is not in the allowed choices.",
                    details={"label": label, "choices": normalized},
                ),
            )
        return StructuredOutput(label, None)

    def _parse_tool_call(self, calls: Any, model: type[BaseModel], *, field: str) -> StructuredOutput:
        if not isinstance(calls, list) or not calls:
            return StructuredOutput(None, ErrorPayload(ErrorKind.INVALID_INPUT, "tool call is missing."))
        call = calls[0]
        args = call.get("function", {}).get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as exc:
                return StructuredOutput(
                    None,
                    ErrorPayload(
                        ErrorKind.INVALID_INPUT,
                        "tool arguments are not valid JSON.",
                        details={"error": str(exc)},
                    ),
                )
        if not isinstance(args, dict):
            return StructuredOutput(None, ErrorPayload(ErrorKind.INVALID_INPUT, "tool arguments must be an object."))
        try:
            payload = model(**args)
        except ValidationError as exc:
            return StructuredOutput(
                None,
                ErrorPayload(
                    ErrorKind.INVALID_INPUT,
                    "tool arguments failed validation.",
                    details={"errors": exc.errors()},
                ),
            )
        value = getattr(payload, field, None)
        return StructuredOutput(value, None)
