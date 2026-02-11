"""Unified tool registry."""

from __future__ import annotations

import builtins
import json
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from loguru import logger
from pydantic import BaseModel
from republic import Tool, ToolContext, tool_from_model

HandlerT = TypeVar("HandlerT", bound=Callable)
P = ParamSpec("P")
T = TypeVar("T")


def _shorten_text(text: str, width: int = 30, placeholder: str = "...") -> str:
    """Shorten text to width characters, cutting in the middle of words if needed.

    Unlike textwrap.shorten, this function can cut in the middle of a word,
    ensuring long strings without spaces are still truncated properly.
    """
    if len(text) <= width:
        return text

    # Reserve space for placeholder
    available = width - len(placeholder)
    if available <= 0:
        return placeholder

    return text[:available] + placeholder


@dataclass(frozen=True)
class ToolDescriptor:
    """Tool metadata and runtime handle."""

    name: str
    short_description: str
    detail: str
    tool: Tool
    source: str = "builtin"


class ToolRegistry:
    """Registry for built-in tools, internal commands, and skill-backed tools."""

    def __init__(self, allowed_tools: set[str] | None = None) -> None:
        self._tools: dict[str, ToolDescriptor] = {}
        self._allowed_tools = allowed_tools

    def register(
        self,
        *,
        name: str,
        short_description: str,
        detail: str | None = None,
        model: type[BaseModel] | None = None,
        context: bool = False,
        source: str = "builtin",
    ) -> Callable[[Callable], ToolDescriptor | None]:
        def decorator(func: Callable[P, T]) -> ToolDescriptor | None:
            tool_detail = detail or func.__doc__ or ""
            if (
                self._allowed_tools is not None
                and name.casefold() not in self._allowed_tools
                and self.to_model_name(name).casefold() not in self._allowed_tools
            ):
                return None

            @wraps(func)
            def handler(*args: Any, **kwargs: Any) -> T:
                context_arg = kwargs.get("context") if context else None
                call_kwargs = {key: value for key, value in kwargs.items() if key != "context"}
                if args and isinstance(args[0], BaseModel):
                    call_kwargs.update(args[0].model_dump())
                self._log_tool_call(name, call_kwargs, context_arg)

                start = time.monotonic()
                try:
                    return func(*args, **kwargs)
                except Exception:
                    logger.exception("tool.call.error name={}", name)
                    raise
                finally:
                    duration = time.monotonic() - start
                    logger.info("tool.call.end name={} duration={:.3f}ms", name, duration * 1000)

            if model is not None:
                tool = tool_from_model(model, handler, name=name, description=short_description, context=context)
            else:
                tool = Tool.from_callable(handler, name=name, description=short_description, context=context)
            tool_desc = ToolDescriptor(
                name=name, short_description=short_description, detail=tool_detail, tool=tool, source=source
            )
            self._tools[name] = tool_desc
            return tool_desc

        return decorator

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)

    def descriptors(self) -> builtins.list[ToolDescriptor]:
        return sorted(self._tools.values(), key=lambda item: item.name)

    @staticmethod
    def to_model_name(name: str) -> str:
        return name.replace(".", "_")

    def compact_rows(self, *, for_model: bool = False) -> builtins.list[str]:
        rows: builtins.list[str] = []
        for descriptor in self.descriptors():
            display_name = self.to_model_name(descriptor.name) if for_model else descriptor.name
            if for_model and display_name != descriptor.name:
                rows.append(f"{display_name} (command: {descriptor.name}): {descriptor.short_description}")
            else:
                rows.append(f"{display_name}: {descriptor.short_description}")
        return rows

    def detail(self, name: str, *, for_model: bool = False) -> str:
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(name)

        schema = descriptor.tool.schema()
        display_name = descriptor.name
        command_name_line = ""
        if for_model:
            schema = deepcopy(schema)
            display_name = self.to_model_name(descriptor.name)
            function = schema.get("function")
            if isinstance(function, dict):
                function["name"] = display_name
            if display_name != descriptor.name:
                command_name_line = f"command_name: {descriptor.name}\n"

        return (
            f"name: {display_name}\n"
            f"{command_name_line}"
            f"source: {descriptor.source}\n"
            f"description: {descriptor.short_description}\n"
            f"detail: {descriptor.detail}\n"
            f"schema: {schema}"
        )

    def model_tools(self) -> builtins.list[Tool]:
        tools: builtins.list[Tool] = []
        seen_names: set[str] = set()
        for descriptor in self.descriptors():
            model_name = self.to_model_name(descriptor.name)
            if model_name in seen_names:
                raise ValueError(f"Duplicate model tool name after conversion: {model_name}")
            seen_names.add(model_name)

            base = descriptor.tool
            tools.append(
                Tool(
                    name=model_name,
                    description=base.description,
                    parameters=base.parameters,
                    handler=base.handler,
                    context=base.context,
                )
            )
        return tools

    def _log_tool_call(self, name: str, kwargs: dict[str, Any], context: ToolContext | None) -> None:
        params: list[str] = []
        for key, value in kwargs.items():
            try:
                rendered = json.dumps(value, ensure_ascii=False)
            except TypeError:
                rendered = repr(value)
            value = _shorten_text(rendered, width=60, placeholder="...")
            if value.startswith('"') and not value.endswith('"'):
                value = value + '"'
            if value.startswith("{") and not value.endswith("}"):
                value = value + "}"
            if value.startswith("[") and not value.endswith("]"):
                value = value + "]"
            params.append(f"{key}={value}")
        params_str = ", ".join(params)
        tape = context.tape if context is not None else "-"
        logger.info("tool.call.start tape={} {{ {} }}", tape, params_str)

    def execute(
        self,
        name: str,
        *,
        kwargs: dict[str, Any],
        context: ToolContext | None = None,
    ) -> Any:
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(name)

        if descriptor.tool.context:
            return descriptor.tool.run(context=context, **kwargs)
        return descriptor.tool.run(**kwargs)
