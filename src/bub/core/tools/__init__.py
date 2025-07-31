"""Tools package for Bub."""

import contextlib
from pathlib import Path
from typing import Any

from .base import Tool, ToolExecutor, ToolResult
from .base import ToolRegistry as BaseToolRegistry
from .commands import RunCommandTool
from .file_ops import FileEditTool, FileReadTool, FileWriteTool


class ToolRegistry(BaseToolRegistry):
    """Simple tool registry for the agent."""

    def __init__(self, workspace_path: Path) -> None:
        """Initialize the tool registry.

        Args:
            workspace_path: Path to the workspace
        """
        super().__init__()
        self.workspace_path = workspace_path
        self._tools: dict[str, type[Tool]] = {}
        self._tool_instances: dict[str, Tool] = {}

        # Auto-register available tools
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools."""
        default_tools = [
            RunCommandTool,
            FileReadTool,
            FileWriteTool,
            FileEditTool,
        ]

        for tool_class in default_tools:
            self.register_tool(tool_class)

    def register_tool(self, tool: Tool | type[Tool]) -> None:
        """Register a tool.

        Args:
            tool: Tool class or instance to register
        """
        if isinstance(tool, type):
            # Register tool class - we need to create an instance to get the name
            # This is a bit tricky since Tool is abstract, so we'll handle it differently
            if hasattr(tool, "get_tool_info"):
                tool_info = tool.get_tool_info()
                self._tools[tool_info["name"]] = tool
                # Create a minimal instance for schema access
                with contextlib.suppress(Exception):
                    tool_instance = tool()
                    self._tool_instances[tool_info["name"]] = tool_instance
        else:
            # Register tool instance
            self._tools[tool.name] = type(tool)
            self._tool_instances[tool.name] = tool

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_schemas(self) -> dict[str, Any]:
        """Get tool schemas.

        Returns:
            Dictionary of tool schemas
        """
        return {name: tool.schema for name, tool in self._tool_instances.items()}

    def _format_schemas_for_context(self) -> str:
        """Format schemas for context.

        Returns:
            Formatted schemas string
        """
        schemas = []
        for name, tool in self._tool_instances.items():
            schemas.append(f"{name}: {tool.description}")
        return "; ".join(schemas)

    def get_tool(self, tool_name: str) -> Any:
        """Get a tool class by name.

        Args:
            tool_name: Name of the tool to get

        Returns:
            Tool class or None if not found
        """
        return self._tools.get(tool_name)

    def get_tool_schema(self, tool_name: str) -> Any:
        """Get the JSON schema for a tool.

        Args:
            tool_name: Name of the tool to get schema for

        Returns:
            Tool schema or None if not found
        """
        tool_instance = self._tool_instances.get(tool_name)
        if tool_instance and hasattr(tool_instance, "get_schema"):
            return tool_instance.get_schema()
        return None


__all__ = [
    "FileEditTool",
    "FileReadTool",
    "FileWriteTool",
    "RunCommandTool",
    "Tool",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
]
