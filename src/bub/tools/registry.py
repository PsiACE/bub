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
        self._tools[descriptor.name] = descriptor

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
            value = textwrap.shorten(json.dumps(value), width=30, placeholder="...")
            if value.startswith('"') and not value.endswith('"'):
                value = value + '"'
            if value.startswith("{") and not value.endswith("}"):
                value = value + "}"
            if value.startswith("[") and not value.endswith("]"):
                value = value + "]"
            params.append(f"{key}={value}")
        params_str = ", ".join(params)
        logger.info("tool.call.start name={} {{ {} }}", name, params_str)

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

        self._log_tool_call(name, kwargs, context)
        start = time.monotonic()
        try:
            if descriptor.tool.context:
                return descriptor.tool.run(context=context, **kwargs)
            return descriptor.tool.run(**kwargs)
        except Exception:
            logger.exception("tool.call.error name={}", name)
            raise
        finally:
            duration = time.monotonic() - start
            logger.info("tool.call.end name={} duration={:.3f}ms", name, duration * 1000)
