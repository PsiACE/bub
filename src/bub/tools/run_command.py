"""Command execution tool for Bub."""

import shlex
import subprocess
from typing import Any, ClassVar, Optional

from pydantic import Field

from ..agent.context import Context
from ..agent.tools import Tool, ToolResult


class RunCommandTool(Tool):
    """Tool for executing terminal commands in the workspace.

    Usage example:
        Action: run_command
        Action Input: {"command": "ls -la"}

    Parameters:
        command: The shell command to execute (e.g., 'ls', 'cat file.txt').
        cwd: Optional. The working directory to run the command in. Defaults to workspace root.
    """

    name: str = Field(default="run_command", description="The internal name of the tool")
    display_name: str = Field(default="Run Command", description="The user-friendly display name")
    description: str = Field(
        default="Execute a terminal command in the workspace", description="Description of what the tool does"
    )

    command: str = Field(..., description="The shell command to execute, e.g., 'ls', 'cat file.txt'.")
    cwd: Optional[str] = Field(
        default=None, description="Optional. The working directory to run the command in. Defaults to workspace root."
    )

    # List of dangerous commands that should be blocked
    DANGEROUS_COMMANDS: ClassVar[set[str]] = {
        "rm",
        "del",
        "format",
        "mkfs",
        "dd",
        "shred",
        "wipe",
        "fdisk",
        "chmod",
        "chown",
        "sudo",
        "su",
        "passwd",
        "useradd",
        "userdel",
        "systemctl",
        "service",
        "init",
        "killall",
        "pkill",
        "kill",
    }

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "run_command",
            "display_name": "Run Command",
            "description": "Execute a terminal command in the workspace",
        }

    def _validate_command(self) -> Optional[str]:
        """Validate command for security."""
        # Check for dangerous commands
        cmd_parts = shlex.split(self.command.lower())
        if not cmd_parts:
            return "Empty command"

        base_cmd = cmd_parts[0]
        if base_cmd in self.DANGEROUS_COMMANDS:
            return f"Dangerous command blocked: {base_cmd}"

        # Check for shell injection attempts
        dangerous_chars = [";", "&&", "||", "|", ">", "<", "`", "$(", "eval", "exec"]
        for char in dangerous_chars:
            if char in self.command:
                return f"Potentially dangerous command pattern: {char}"

        return None

    def execute(self, context: Context) -> ToolResult:
        """Execute the command."""
        try:
            # Validate command first
            validation_error = self._validate_command()
            if validation_error:
                return ToolResult(success=False, data=None, error=validation_error)

            working_dir = self.cwd
            if not working_dir:
                working_dir = str(context.workspace_path)

            cmd_parts = shlex.split(self.command)
            result = subprocess.run(  # noqa: S603
                cmd_parts,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return ToolResult(
                success=(result.returncode == 0),
                data={"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
                error=None if result.returncode == 0 else f"Command failed with return code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, data=None, error="Command timed out after 30 seconds")
        except Exception as e:
            # detailed feedback for all exceptions
            import traceback

            tb = traceback.format_exc()
            return ToolResult(success=False, data=None, error=f"Error executing command: {e!s}\nTraceback:\n{tb}")
