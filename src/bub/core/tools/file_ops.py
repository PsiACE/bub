"""File operations tools for Bub."""

from pathlib import Path
from typing import Any, Literal, Optional

import logfire
from pydantic import Field

from ...core.context import AgentContext
from .base import Tool, ToolResult

# Common ignore patterns inspired by crush's CommonIgnorePatterns
COMMON_IGNORE_PATTERNS = {
    # Version control
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    # IDE and editor files
    ".vscode",
    ".idea",
    "*.swp",
    "*.swo",
    "*~",
    ".DS_Store",
    "Thumbs.db",
    # Build artifacts and dependencies
    "node_modules",
    "target",
    "build",
    "dist",
    "out",
    "bin",
    "obj",
    "*.o",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    # Logs and temporary files
    "*.log",
    "*.tmp",
    "*.temp",
    ".cache",
    ".tmp",
    # Language-specific
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    "vendor",
    "Cargo.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    # OS generated files
    ".Trash",
    ".Spotlight-V100",
    ".fseventsd",
    # Bub specific
    ".bub",
}


def _check_common_patterns(path: Path) -> bool:
    """Check if path matches common ignore patterns."""
    for pattern in COMMON_IGNORE_PATTERNS:
        if pattern.startswith("*"):
            # Wildcard pattern
            if path.name.endswith(pattern[1:]):
                return True
        else:
            # Exact match
            if path.name == pattern or any(part == pattern for part in path.parts):
                return True
    return False


def _check_gitignore_patterns(rel_path: Path, workspace_path: Path) -> bool:
    """Check if path matches gitignore patterns."""
    gitignore_path = workspace_path / ".gitignore"
    if not gitignore_path.exists():
        return False

    try:
        with open(gitignore_path, encoding="utf-8") as f:
            gitignore_patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        for pattern in gitignore_patterns:
            if pattern.startswith("/"):
                # Absolute pattern from workspace root
                if str(rel_path) == pattern[1:] or str(rel_path).startswith(pattern[1:] + "/"):
                    return True
            elif pattern.endswith("/"):
                # Directory pattern
                if str(rel_path).startswith(pattern[:-1]):
                    return True
            else:
                # File pattern
                if str(rel_path) == pattern or str(rel_path).endswith("/" + pattern):
                    return True
    except Exception:
        logfire.exception("Error checking gitignore patterns")

    return False


def should_ignore_path(path: Path, workspace_path: Path) -> bool:
    """Check if a path should be ignored based on common patterns and gitignore."""
    try:
        rel_path = path.relative_to(workspace_path)
    except ValueError:
        # Path is outside workspace, check if it's hidden
        return path.name.startswith(".")

    # Check for hidden files/directories
    if path.name.startswith("."):
        return True

    # Check common ignore patterns
    if _check_common_patterns(path):
        return True

    # Check gitignore patterns
    return _check_gitignore_patterns(rel_path, workspace_path)


def is_binary_file(file_path: Path, sample_size: int = 1024) -> bool:
    """Detect if a file is binary by checking for null bytes in the first sample_size bytes."""
    try:
        with open(file_path, "rb") as f:
            sample = f.read(sample_size)
            return b"\x00" in sample
    except Exception:
        return False


def validate_file_path(file_path: Path, workspace_path: Path) -> tuple[bool, Optional[str]]:
    """Validate file path for security and accessibility."""
    try:
        # Resolve to absolute path
        abs_path = file_path.resolve()
        workspace_abs = workspace_path.resolve()

        # Check if path is within workspace
        try:
            abs_path.relative_to(workspace_abs)
        except ValueError:
            return False, "Path is outside workspace"

        # Check for path traversal attempts
        if ".." in str(file_path):
            return False, "Path traversal not allowed"

    except Exception as e:
        return False, f"Invalid path: {e}"

    return True, None


class FileReadTool(Tool):
    """Read the contents of a file in the workspace.

    This tool reads text files and returns their content. It automatically filters out
    binary files, hidden files, and files that should be ignored based on .gitignore
    and common ignore patterns.

    Usage example:
        Action: read_file
        Action Input: {"path": "config.txt"}

    Parameters:
        path: The relative or absolute path to the file to read.
    """

    name: str = Field(default="read_file", description="The internal name of the tool")
    display_name: str = Field(default="Read File", description="The user-friendly display name")
    description: str = Field(default=__doc__, description="Description of what the tool does")

    path: str = Field(..., description="The relative or absolute path to the file to read.")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "read_file",
            "display_name": "Read File",
            "description": cls.__doc__,
        }

    def execute(self, context: AgentContext) -> ToolResult:
        """Execute the file read operation."""
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            # Validate path
            is_valid, error_msg = validate_file_path(file_path, context.workspace_path)
            if not is_valid:
                return ToolResult(success=False, data=None, error=error_msg)

            if not file_path.exists():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File not found: {safe_path}")

            if not file_path.is_file():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"Path is not a file: {safe_path}")

            # Check if file should be ignored
            if should_ignore_path(file_path, context.workspace_path):
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File is ignored: {safe_path}")

            # Check if file is binary
            if is_binary_file(file_path):
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File is binary: {safe_path}")

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
    """Write content to a file in the workspace.

    This tool creates or overwrites files with the specified content. It automatically
    creates parent directories if they don't exist and supports both overwrite and
    append modes.

    Usage example:
        Action: write_file
        Action Input: {"path": "output.txt", "content": "Hello, world!", "mode": "overwrite"}

    Parameters:
        path: The relative or absolute path to the file to write.
        content: The content to write to the file.
        mode: Write mode - "overwrite" (default) or "append".
    """

    name: str = Field(default="write_file", description="The internal name of the tool")
    display_name: str = Field(default="Write File", description="The user-friendly display name")
    description: str = Field(default=__doc__, description="Description of what the tool does")

    path: str = Field(..., description="The relative or absolute path to the file to write.")
    content: str = Field(..., description="The content to write to the file.")
    mode: str = Field(default="overwrite", description="Write mode: 'overwrite' or 'append'")

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "write_file",
            "display_name": "Write File",
            "description": cls.__doc__,
        }

    def execute(self, context: AgentContext) -> ToolResult:
        """Execute the file write operation."""
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            # Validate path
            is_valid, error_msg = validate_file_path(file_path, context.workspace_path)
            if not is_valid:
                return ToolResult(success=False, data=None, error=error_msg)

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
    """Edit file content with fine-grained operations.

    This tool provides precise editing capabilities for text files, including line-based
    operations, text replacement, and content insertion. It automatically validates paths
    and filters out binary or ignored files.

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
    description: str = Field(default=__doc__, description="Description of what the tool does")

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
            "description": cls.__doc__,
        }

    def execute(self, context: AgentContext) -> ToolResult:
        try:
            from .utils import sanitize_path

            file_path = Path(self.path)
            if not file_path.is_absolute():
                file_path = context.workspace_path / file_path

            # Validate path
            is_valid, error_msg = validate_file_path(file_path, context.workspace_path)
            if not is_valid:
                return ToolResult(success=False, data=None, error=error_msg)

            if not file_path.exists():
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File not found: {safe_path}")

            # Check if file should be ignored
            if should_ignore_path(file_path, context.workspace_path):
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File is ignored: {safe_path}")

            # Check if file is binary
            if is_binary_file(file_path):
                safe_path = sanitize_path(file_path)
                return ToolResult(success=False, data=None, error=f"File is binary: {safe_path}")

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

    def _replace_lines(self, lines: list[str], file_path: Path) -> ToolResult:
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

    def _replace_text(self, lines: list[str], file_path: Path) -> ToolResult:
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

    def _insert_after(self, lines: list[str], file_path: Path) -> ToolResult:
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

    def _insert_before(self, lines: list[str], file_path: Path) -> ToolResult:
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

    def _delete_lines(self, lines: list[str], file_path: Path) -> ToolResult:
        from .utils import sanitize_path

        if self.start_line is None or self.end_line is None:
            return ToolResult(success=False, data=None, error="start_line and end_line are required for delete_lines.")
        if not (1 <= self.start_line <= self.end_line <= len(lines)):
            return ToolResult(success=False, data=None, error="Invalid line range.")
        new_lines = lines[: self.start_line - 1] + lines[self.end_line :]
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _append(self, lines: list[str], file_path: Path) -> ToolResult:
        from .utils import sanitize_path

        if self.content is None:
            return ToolResult(success=False, data=None, error="content is required for append.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = lines + new_content_lines
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)

    def _prepend(self, lines: list[str], file_path: Path) -> ToolResult:
        from .utils import sanitize_path

        if self.content is None:
            return ToolResult(success=False, data=None, error="content is required for prepend.")
        new_content_lines = self.content.splitlines(keepends=True)
        new_lines = new_content_lines + lines
        file_path.write_text("".join(new_lines), encoding="utf-8")
        safe_path = sanitize_path(file_path)
        return ToolResult(success=True, data=f"File edited successfully: {safe_path}", error=None)
