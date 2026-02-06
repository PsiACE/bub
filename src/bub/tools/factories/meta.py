"""Meta and utility tool factories."""

from __future__ import annotations

from collections.abc import Callable

from republic import Tool, tool_from_model

from .shared import EmptyInput


def create_help_tool(render_help: Callable[[], str]) -> Tool:
    """Create the help tool."""

    def _handler(_params: EmptyInput) -> str:
        return str(render_help())

    return tool_from_model(
        EmptyInput,
        _handler,
        name="help",
        description="Show available commands",
    )


def create_tools_tool(render_tools: Callable[[], str]) -> Tool:
    """Create the tools tool."""

    def _handler(_params: EmptyInput) -> str:
        return str(render_tools())

    return tool_from_model(
        EmptyInput,
        _handler,
        name="tools",
        description="Show available tools",
    )


def create_static_tool(name: str, description: str, value: str) -> Tool:
    """Create a static response tool."""

    def _handler(_params: EmptyInput) -> str:
        return value

    return tool_from_model(
        EmptyInput,
        _handler,
        name=name,
        description=description,
    )
