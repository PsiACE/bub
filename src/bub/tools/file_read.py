"""File read tool for Bub."""

from typing import Any

from pydantic import Field

from ..agent.context import Context
from ..agent.tools import Tool, ToolResult


class FileReadTool(Tool):
    """Tool for reading file contents from the workspace.

    Usage example:
        Action: read_file
        Action Input: {"path": "README.md"}

    Parameters:
        path: The relative or absolute path to the file to read.
    """

    name: str = Field(default="read_file", description="The internal name of the tool")
    display_name: str = Field(default="Read File", description="The user-friendly display name")
    description: str = Field(
        default="Read the contents of a file from the workspace", description="Description of what the tool does"
    )

    path: str = Field(..., description="The relative or absolute path to the file to read.")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "read_file",
            "display_name": "Read File",
            "description": "Read the contents of a file from the workspace",
        }

    def execute(self, context: Context) -> ToolResult:
        """Execute the file read operation."""
        try:
            from pathlib import Path

            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            if not file_path.exists():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File not found: {safe_path}")

            content = file_path.read_text(encoding="utf-8")
            return ToolResult(success=True, data=content, error=None)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error reading file: {e!s}")
