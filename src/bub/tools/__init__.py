"""Tools package for Bub."""

from republic import Tool

from ..agent.context import Context
from .catalog import ToolCatalog, ToolSpec, build_tool_catalog


def build_agent_tools(context: Context, catalog: ToolCatalog | None = None) -> list[Tool]:
    """Build the tool set for the agent runtime."""
    catalog = catalog or build_tool_catalog()
    return catalog.build_tools(context, audience="agent")


def build_cli_tools(context: Context, catalog: ToolCatalog | None = None) -> list[Tool]:
    """Build the tool set for the CLI runtime."""
    catalog = catalog or build_tool_catalog()
    return catalog.build_tools(context, audience="cli")


__all__ = [
    "Tool",
    "ToolCatalog",
    "ToolSpec",
    "build_agent_tools",
    "build_cli_tools",
    "build_tool_catalog",
]
