"""Tool registry and execution for Bub."""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from .context import Context


class ToolResult(BaseModel):
    """Result of a tool execution."""

    success: bool = Field(..., description="Whether the tool execution was successful")
    data: Any = Field(..., description="Tool execution result data")
    error: Optional[str] = Field(None, description="Error message if failed")

    def format_result(self) -> str:
        """Format the result for display."""
        output = []
        if isinstance(self.data, dict) and ("stdout" in self.data or "stderr" in self.data):
            if self.data.get("stdout", "").strip():
                output.append(f"Output:\n{self.data['stdout']}")
            if self.data.get("stderr", "").strip():
                output.append(f"Errors:\n{self.data['stderr']}")
        if self.success:
            if output:
                return "\n".join(output)
            elif isinstance(self.data, dict):
                return "Command executed successfully"
            else:
                return str(self.data)
        else:
            error_msg = f"Error: {self.error}"
            return "\n".join([error_msg, *output]) if output else error_msg


class Tool(ABC, BaseModel):
    """Abstract base class for all tools with self-contained metadata."""

    name: str = Field(..., description="The internal name of the tool (used for API calls)")
    display_name: str = Field(..., description="The user-friendly display name of the tool")
    description: str = Field(..., description="Description of what the tool does")

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata without creating an instance."""
        # This should be overridden by subclasses to provide their specific info
        return {"name": "base_tool", "display_name": "Base Tool", "description": "Base tool class"}

    def get_schema(self) -> dict[str, Any]:
        """Get the JSON schema for this tool."""
        return self.model_json_schema()

    def get_function_declaration(self) -> dict[str, Any]:
        """Get the function declaration schema for this tool."""
        return {"name": self.name, "description": self.description, "parameters": self.get_schema()}

    def validate_params(self, params: dict[str, Any]) -> Optional[str]:
        """Validate parameters for the tool. Returns error message if invalid, None if valid."""
        try:
            # Create a temporary instance to validate parameters
            self.__class__(**params)
        except ValidationError as e:
            return f"Parameter validation failed: {e.errors()}"
        else:
            return None

    def get_description(self, params: dict[str, Any]) -> str:
        """Get a pre-execution description of the tool operation."""
        return f"Executing {self.display_name} with parameters: {json.dumps(params, indent=2)}"

    @abstractmethod
    def execute(self, context: Context) -> ToolResult:
        """Execute the tool with the given context."""
        pass


class ToolExecutor:
    """Executes tools based on agent requests."""

    def __init__(self, context: Context) -> None:
        self.context = context
        self.tool_registry: Optional[Any] = getattr(context, "tool_registry", None)

    def execute_tool(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool with given parameters."""
        if self.tool_registry is None:
            return ToolResult(success=False, data=None, error="Tool registry is not initialized.")
        tool_class = self.tool_registry.get_tool(tool_name)
        if not tool_class:
            return ToolResult(success=False, data=None, error=f"Tool not found: {tool_name}")

        try:
            # Create tool instance with parameters
            tool_instance = tool_class(**kwargs)

            # Execute the tool with context
            result: ToolResult = tool_instance.execute(self.context)
        except ValidationError as ve:
            return ToolResult(success=False, data=None, error=f"Parameter validation failed: {ve.errors()}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Tool execution failed: {e!s}")
        else:
            return result

    def extract_tool_calls(self, response: str) -> list[dict[str, Any]]:
        """Extract tool calls from the response (ReAct/Action Input pattern)."""
        tool_calls: list[dict[str, Any]] = []
        # Support both code block and ReAct Action/Action Input pattern
        # 1. Code block (legacy)
        tool_pattern = r"```tool\s*\n(.*?)\n```"
        matches = re.findall(tool_pattern, response, re.DOTALL)
        for match in matches:
            try:
                tool_call = json.loads(match)
                if isinstance(tool_call, dict) and "tool" in tool_call:
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue
        # 2. ReAct Action/Action Input pattern
        action_pattern = r"Action:\s*(\w+)\s*\nAction Input:\s*(\{.*?\})(?:\n|$)"
        for action, action_input in re.findall(action_pattern, response, re.DOTALL):
            try:
                params = json.loads(action_input)
                tool_calls.append({"tool": action, "parameters": params})
            except json.JSONDecodeError:
                continue
        return tool_calls

    def execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> str:
        """Execute tool calls and return results in Observation format."""
        results: list[str] = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            parameters = tool_call.get("parameters", {})
            if not tool_name:
                continue
            result = self.execute_tool(tool_name, **parameters)
            # ReAct Observation format
            results.append(f"Observation: {result.format_result()}")
        return "\n".join(results) if results else "No tools executed."


class ToolRegistry:
    """Registry for available tools."""

    def __init__(self) -> None:
        self.tools: dict[str, type[Tool]] = {}

    def register_tool(self, tool_class: type[Tool]) -> None:
        """Register a tool class."""
        # Get tool info from class method
        tool_info = tool_class.get_tool_info()
        self.tools[tool_info["name"]] = tool_class

    def register_default_tools(self) -> None:
        """Register the default set of tools."""
        try:
            from ..tools.file_edit import FileEditTool
            from ..tools.file_read import FileReadTool
            from ..tools.file_write import FileWriteTool
            from ..tools.run_command import RunCommandTool

            self.register_tool(RunCommandTool)
            self.register_tool(FileReadTool)
            self.register_tool(FileWriteTool)
            self.register_tool(FileEditTool)
        except ImportError as e:
            print(f"Warning: Could not load some tools: {e}")

    def get_tool(self, tool_name: str) -> Optional[type[Tool]]:
        """Get a tool class by name."""
        return self.tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """List all available tool names."""
        return list(self.tools.keys())

    def get_tool_schemas(self) -> dict[str, Any]:
        """Get all tool schemas."""
        schemas = {}
        for name, tool_class in self.tools.items():
            tool_info = tool_class.get_tool_info()
            # Get the schema directly from the class without creating an instance
            schema = tool_class.model_json_schema()
            schemas[name] = {"name": tool_info["name"], "description": tool_info["description"], "parameters": schema}
        return schemas

    def get_tool_schema(self, tool_name: str) -> Optional[dict[str, Any]]:
        """Get the JSON schema for a tool."""
        tool_class = self.get_tool(tool_name)
        if tool_class:
            tool_info = tool_class.get_tool_info()
            schema = tool_class.model_json_schema()
            return {"name": tool_info["name"], "description": tool_info["description"], "parameters": schema}
        return None

    def _format_schemas_for_context(self) -> str:
        """Format tool schemas for context message."""
        schemas = self.get_tool_schemas()
        return json.dumps(schemas, indent=2)
