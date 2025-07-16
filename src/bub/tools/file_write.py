"""File write tool for Bub."""

from typing import Any

from pydantic import Field

from ..agent.context import Context
from ..agent.tools import Tool, ToolResult


class FileWriteTool(Tool):
    """Tool for writing content to files in the workspace.

    Usage example:
        Action: write_file
        Action Input: {"path": "output.txt", "content": "Hello, World!"}

    Parameters:
        path: The relative or absolute path to the file to write.
        content: The text content to write to the file.
    """

    name: str = Field(default="write_file", description="The internal name of the tool")
    display_name: str = Field(default="Write File", description="The user-friendly display name")
    description: str = Field(
        default="Write content to a file in the workspace", description="Description of what the tool does"
    )

    path: str = Field(..., description="The relative or absolute path to the file to write.")
    content: str = Field(..., description="The text content to write to the file.")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "write_file",
            "display_name": "Write File",
            "description": "Write content to a file in the workspace",
        }

    def execute(self, context: Context) -> ToolResult:
        """Execute the file write operation."""
        try:
            from pathlib import Path

            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(self.content, encoding="utf-8")
            safe_path = sanitize_path(file_path)
            return ToolResult(success=True, data=f"File written successfully: {safe_path}", error=None)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error writing file: {e!s}")
