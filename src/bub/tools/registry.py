"""Unified tool registry."""

from __future__ import annotations

import builtins
import json
import textwrap
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger
from republic import Tool, ToolContext


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

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        wrapped_tool = self._wrap_tool(descriptor.tool)
        self._tools[descriptor.name] = ToolDescriptor(
            name=descriptor.name,
            short_description=descriptor.short_description,
            detail=descriptor.detail,
            tool=wrapped_tool,
            source=descriptor.source,
        )

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)

    def descriptors(self) -> builtins.list[ToolDescriptor]:
        return sorted(self._tools.values(), key=lambda item: item.name)

    def compact_rows(self) -> builtins.list[str]:
        rows: builtins.list[str] = []
        for descriptor in self.descriptors():
            rows.append(f"{descriptor.name}: {descriptor.short_description}")
        return rows

    def detail(self, name: str) -> str:
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(name)

        schema = descriptor.tool.schema()
        return (
            f"name: {descriptor.name}\n"
            f"source: {descriptor.source}\n"
            f"description: {descriptor.short_description}\n"
            f"detail: {descriptor.detail}\n"
            f"schema: {schema}"
        )

    def _log_tool_call(self, name: str, kwargs: dict[str, Any], context: ToolContext | None) -> None:
        params: list[str] = []
        for key, value in kwargs.items():
            try:
                rendered = json.dumps(value, ensure_ascii=False)
            except TypeError:
                rendered = repr(value)
            value = textwrap.shorten(rendered, width=30, placeholder="...")
            if value.startswith('"') and not value.endswith('"'):
                value = value + '"'
            if value.startswith("{") and not value.endswith("}"):
                value = value + "}"
            if value.startswith("[") and not value.endswith("]"):
                value = value + "]"
            params.append(f"{key}={value}")
        params_str = ", ".join(params)
        run_id = context.run_id if context is not None else "-"
        tape = context.tape if context is not None else "-"
        logger.info(
            "tool.call.start name={} run_id={} tape={} {{ {} }}",
            name,
            run_id,
            tape,
            params_str,
        )

    def _wrap_tool(self, tool: Tool) -> Tool:
        if tool.handler is None:
            return tool

        original_tool = tool

        def _handler(*args: Any, **kwargs: Any) -> Any:
            context = kwargs.get("context") if original_tool.context else None
            call_kwargs = {f"arg{idx}": value for idx, value in enumerate(args)}
            call_kwargs.update({key: value for key, value in kwargs.items() if key != "context"})
            self._log_tool_call(original_tool.name, call_kwargs, context)

            start = time.monotonic()
            try:
                return original_tool.run(*args, **kwargs)
            except Exception:
                logger.exception("tool.call.error name={}", original_tool.name)
                raise
            finally:
                duration = time.monotonic() - start
                logger.info("tool.call.end name={} duration={:.3f}ms", original_tool.name, duration * 1000)

        return Tool(
            name=original_tool.name,
            description=original_tool.description,
            parameters=original_tool.parameters,
            handler=_handler,
            context=original_tool.context,
        )

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
