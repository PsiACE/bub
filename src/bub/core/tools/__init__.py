"""Tools package for Bub."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolExecutor, ToolResult
from .commands import RunCommandTool
from .file_ops import FileEditTool, FileReadTool, FileWriteTool


class ToolRegistry:
    """Simple tool registry for the agent."""

    def __init__(self, workspace_path: Path) -> None:
        """Initialize the tool registry.

        Args:
            workspace_path: Path to the workspace
        """
        self.workspace_path = workspace_path
        self._tools: dict[str, type[Tool]] = {}
        self._tool_instances: dict[str, Any] = {}

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
            self.register_tool(tool_class)  # type: ignore[arg-type]

    def register_tool(self, tool: Tool | type[Tool]) -> None:
        """Register a tool.

        Args:
            tool: Tool class or instance to register
        """
        if isinstance(tool, type):
            # Register tool class
            tool_info = tool.get_tool_info()
            self._tools[tool_info["name"]] = tool

            # Create a minimal instance for schema access
            # Use the class itself for schema generation instead of creating an instance
            self._tool_instances[tool_info["name"]] = tool
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
        schemas = {}
        for name, tool in self._tool_instances.items():
            if hasattr(tool, "model_json_schema"):
                schemas[name] = tool.model_json_schema()
            elif hasattr(tool, "schema"):
                schemas[name] = tool.schema
            else:
                schemas[name] = {}
        return schemas

    def _format_schemas_for_context(self) -> str:
        """Format schemas for context.

        Returns:
            Formatted schemas string
        """
        schemas = []
        for name, tool in self._tool_instances.items():
            # Get detailed tool information
            tool_info = tool.get_tool_info() if hasattr(tool, "get_tool_info") else {}
            description = tool_info.get("description", "No description")

            # Get schema for parameters
            schema = tool.model_json_schema() if hasattr(tool, "model_json_schema") else {}
            properties = schema.get("properties", {})

            # Format parameters
            param_list = []
            for param_name, param_info in properties.items():
                # Skip internal tool fields
                if param_name in ["name", "display_name", "description"]:
                    continue

                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "")
                required = param_name in schema.get("required", [])
                param_str = f"{param_name} ({param_type})"
                if param_desc:
                    param_str += f": {param_desc}"
                if required:
                    param_str += " [required]"
                param_list.append(param_str)

            # Build tool description
            tool_desc = f"{name}: {description}"
            if param_list:
                tool_desc += f" | Parameters: {', '.join(param_list)}"

            schemas.append(tool_desc)

        return "\n".join(schemas)

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
