"""File operations tools for Bub."""

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field

from ...core.context import AgentContext
from .base import Tool, ToolResult


class FileReadTool(Tool):
    """Tool for reading file contents in the workspace.

    Usage example:
        Action: read_file
        Action Input: {"path": "config.txt"}

    Parameters:
        path: The relative or absolute path to the file to read.
    """

    name: str = Field(default="read_file", description="The internal name of the tool")
    display_name: str = Field(default="Read File", description="The user-friendly display name")
    description: str = Field(default="Read the contents of a file", description="Description of what the tool does")

    path: str = Field(..., description="The relative or absolute path to the file to read.")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "read_file",
            "display_name": "Read File",
            "description": "Read the contents of a file",
        }

    def execute(self, context: AgentContext) -> ToolResult:
        """Execute the file read operation."""
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            if not file_path.exists():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File not found: {safe_path}")

            if not file_path.is_file():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"Path is not a file: {safe_path}")

            try:
                content = file_path.read_text(encoding="utf-8")
                safe_path = sanitize_path(file_path)
                return ToolResult(success=True, data=content, error=None)
            except UnicodeDecodeError:
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File is not a text file: {safe_path}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error reading file: {e!s}")


class FileWriteTool(Tool):
    """Tool for writing content to files in the workspace.

    Usage example:
        Action: write_file
        Action Input: {"path": "output.txt", "content": "Hello, world!"}

    Parameters:
        path: The relative or absolute path to the file to write.
        content: The content to write to the file.
        mode: Write mode - "overwrite" (default) or "append".
    """

    name: str = Field(default="write_file", description="The internal name of the tool")
    display_name: str = Field(default="Write File", description="The user-friendly display name")
    description: str = Field(default="Write content to a file", description="Description of what the tool does")

    path: str = Field(..., description="The relative or absolute path to the file to write.")
    content: str = Field(..., description="The content to write to the file.")
    mode: str = Field(default="overwrite", description="Write mode: 'overwrite' or 'append'")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "write_file",
            "display_name": "Write File",
            "description": "Write content to a file",
        }

    def execute(self, context: AgentContext) -> ToolResult:
        """Execute the file write operation."""
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if self.mode == "append" and file_path.exists():
                # Append mode
                existing_content = file_path.read_text(encoding="utf-8")
                new_content = existing_content + self.content
                file_path.write_text(new_content, encoding="utf-8")
            else:
                # Overwrite mode (default)
                file_path.write_text(self.content, encoding="utf-8")

            safe_path = sanitize_path(file_path)
            return ToolResult(success=True, data=f"File written successfully: {safe_path}", error=None)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error writing file: {e!s}")


class FileEditTool(Tool):
    """Tool for fine-grained editing of file contents in the workspace.

    Usage example:
        Action: edit_file
        Action Input: {"path": "config.txt", "operation": "replace_lines", "start_line": 1, "end_line": 3, "content": "new content"}

    Parameters:
        path: The relative or absolute path to the file to edit.
        operation: The type of edit operation.
        content: The content to use in the operation.
        start_line: Start line number (1-based, inclusive). For line-based ops.
        end_line: End line number (1-based, inclusive). For line-based ops.
        match_text: Text to match for replace_text operation.
        replace_text: Replacement text for replace_text operation.
        line_number: Line number for insert_after/insert_before (1-based).

    Supported operations:
        - replace_lines: Replace lines in a given range (1-based, inclusive)
        - replace_text: Replace all occurrences of match_text with replace_text
        - insert_after: Insert content after a given line number
        - insert_before: Insert content before a given line number
        - delete_lines: Delete lines in a given range (1-based, inclusive)
        - append: Append content to the end of the file
        - prepend: Prepend content to the beginning of the file
    """

    name: str = Field(default="edit_file", description="The internal name of the tool")
    display_name: str = Field(default="Edit File", description="The user-friendly display name")
    description: str = Field(
        default="Edit file content with fine-grained operations", description="Description of what the tool does"
    )

    path: str = Field(..., description="The relative or absolute path to the file to edit.")
    operation: Literal[
        "replace_lines", "replace_text", "insert_after", "insert_before", "delete_lines", "append", "prepend"
    ] = Field(..., description="The type of edit operation.")
    content: Optional[str] = Field(None, description="The content to use in the operation.")
    start_line: Optional[int] = Field(None, description="Start line number (1-based, inclusive). For line-based ops.")
    end_line: Optional[int] = Field(None, description="End line number (1-based, inclusive). For line-based ops.")
    match_text: Optional[str] = Field(None, description="Text to match for replace_text operation.")
    replace_text: Optional[str] = Field(None, description="Replacement text for replace_text operation.")
    line_number: Optional[int] = Field(None, description="Line number for insert_after/insert_before (1-based).")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        return {
            "name": "edit_file",
            "display_name": "Edit File",
            "description": "Edit file content with fine-grained operations",
        }

    def execute(self, context: AgentContext) -> ToolResult:
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path
            if not file_path.exists():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File not found: {safe_path}")

            lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            dispatch = {
                "replace_lines": self._replace_lines,
                "replace_text": self._replace_text,
                "insert_after": self._insert_after,
                "insert_before": self._insert_before,
                "delete_lines": self._delete_lines,
                "append": self._append,
                "prepend": self._prepend,
            }
            func = dispatch.get(self.operation)
            if func is None:
                return ToolResult(success=False, data=None, error=f"Unknown operation: {self.operation}")
            return func(lines, file_path)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error editing file: {e!s}")

    def _replace_lines(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.start_line is None or self.end_line is None or self.content is None:
            return ToolResult(
                success=False, data=None, error="start_line, end_line, and content are required for replace_lines."
            )
        if not (1 <= self.start_line <= self.end_line <= len(lines)):
            return ToolResult(success=False, data=None, error="Invalid line range.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = lines[: self.start_line - 1] + new_content_lines + lines[self.end_line :]
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _replace_text(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.match_text is None or self.replace_text is None:
            return ToolResult(
                success=False, data=None, error="match_text and replace_text are required for replace_text."
            )
        file_text = "".join(lines)
        new_text = file_text.replace(self.match_text, self.replace_text)
        new_lines = new_text.splitlines(keepends=True)
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _insert_after(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.line_number is None or self.content is None:
            return ToolResult(success=False, data=None, error="line_number and content are required for insert_after.")
        if not (0 <= self.line_number <= len(lines)):
            return ToolResult(success=False, data=None, error="Invalid line_number.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = lines[: self.line_number] + new_content_lines + lines[self.line_number :]
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _insert_before(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.line_number is None or self.content is None:
            return ToolResult(success=False, data=None, error="line_number and content are required for insert_before.")
        if not (1 <= self.line_number <= len(lines) + 1):
            return ToolResult(success=False, data=None, error="Invalid line_number.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = lines[: self.line_number - 1] + new_content_lines + lines[self.line_number - 1 :]
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _delete_lines(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.start_line is None or self.end_line is None:
            return ToolResult(success=False, data=None, error="start_line and end_line are required for delete_lines.")
        if not (1 <= self.start_line <= self.end_line <= len(lines)):
            return ToolResult(success=False, data=None, error="Invalid line range.")
        new_lines = lines[: self.start_line - 1] + lines[self.end_line :]
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _append(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.content is None:
            return ToolResult(success=False, data=None, error="content is required for append.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = lines + new_content_lines
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _prepend(self, lines: list[str], file_path: Any) -> ToolResult:
        from .utils import sanitize_path

        if self.content is None:
            return ToolResult(success=False, data=None, error="content is required for prepend.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = new_content_lines + lines
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)
