"""Command execution tool for Bub."""

import os
import shlex
import subprocess
import threading
from typing import Any, Callable, ClassVar, Optional

import logfire
from pydantic import Field

from ...core.context import AgentContext
from .base import Tool, ToolResult


class CommandBlocker:
    """Flexible command blocking system inspired by crush's design."""

    def __init__(self) -> None:
        self.block_funcs: list[Callable[[list[str]], bool]] = []

    def add_blocker(self, block_func: Callable[[list[str]], bool]) -> None:
        """Add a blocking function."""
        self.block_funcs.append(block_func)

    def should_block(self, args: list[str]) -> Optional[str]:
        """Check if command should be blocked."""
        for block_func in self.block_funcs:
            if block_func(args):
                return f"Command blocked: {' '.join(args)}"
        return None

    @staticmethod
    def commands_blocker(banned_commands: list[str]) -> Callable[[list[str]], bool]:
        """Create a blocker for exact command matches."""
        banned_set = set(banned_commands)

        def blocker(args: list[str]) -> bool:
            if not args:
                return False
            return args[0] in banned_set

        return blocker

    @staticmethod
    def arguments_blocker(blocked_subcommands: list[list[str]]) -> Callable[[list[str]], bool]:
        """Create a blocker for specific subcommands."""

        def blocker(args: list[str]) -> bool:
            for blocked in blocked_subcommands:
                if len(args) >= len(blocked):
                    match = True
                    for i, part in enumerate(blocked):
                        if args[i] != part:
                            match = False
                            break
                    if match:
                        return True
            return False

        return blocker


class RunCommandTool(Tool):
    """Execute a terminal command in the workspace.

    This tool runs shell commands with comprehensive security measures including
    command validation, working directory restrictions, and timeout handling.
    It automatically blocks dangerous commands and patterns to ensure safety.

    Usage example:
        Action: run_command
        Action Input: {"command": "ls -la", "cwd": "src", "timeout": 30}

    Parameters:
        command: The shell command to execute (e.g., 'ls', 'cat file.txt').
        cwd: Optional. The working directory to run the command in. Defaults to workspace root.
        timeout: Optional. The timeout in seconds for the command to run. Defaults to 30 seconds.

    Security Features:
        - Blocks dangerous commands (rm, sudo, systemctl, etc.)
        - Blocks dangerous patterns (;, &&, ||, |, etc.)
        - Validates working directory is within workspace
        - Sanitizes environment variables
        - Implements command timeout with graceful termination
    """

    name: str = Field(default="run_command", description="The internal name of the tool")
    display_name: str = Field(default="Run Command", description="The user-friendly display name")
    description: str = Field(
        default="Execute a terminal command in the workspace with security measures",
        description="Description of what the tool does",
    )

    command: str = Field(..., description="The shell command to execute, e.g., 'ls', 'cat file.txt'.")
    cwd: Optional[str] = Field(
        default=None, description="Optional. The working directory to run the command in. Defaults to workspace root."
    )
    timeout: int = Field(
        default=30, description="The timeout in seconds for the command to run. Defaults to 30 seconds."
    )

    # Dangerous commands that should be blocked
    DANGEROUS_COMMANDS: ClassVar[set[str]] = {
        # File system operations
        "rm",
        "del",
        "format",
        "mkfs",
        "dd",
        "shred",
        "wipe",
        "fdisk",
        # Permission operations
        "chmod",
        "chown",
        "sudo",
        "su",
        # User management
        "passwd",
        "useradd",
        "userdel",
        "usermod",
        # System services
        "systemctl",
        "service",
        "init",
        "reboot",
        "shutdown",
        "halt",
        # Process management
        "killall",
        "pkill",
        "kill",  # Network operations
        "iptables",
        "firewall-cmd",
        "ufw",
        # Package management
        "apt",
        "yum",
        "dnf",
        "pacman",
        "brew",
        # Shell operations
        "eval",
        "exec",
        "source",
        ".",
    }

    # Dangerous command patterns
    DANGEROUS_PATTERNS: ClassVar[set[str]] = {";", "&&", "||", "|", ">", "<", "`", "$(", "eval", "exec", "source"}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._command_blocker = CommandBlocker()
        self._setup_blockers()

    def _setup_blockers(self) -> None:
        """Setup command blockers."""
        # Block dangerous commands
        self._command_blocker.add_blocker(CommandBlocker.commands_blocker(list(self.DANGEROUS_COMMANDS)))

        # Block dangerous subcommands
        dangerous_subcommands = [
            ["git", "reset", "--hard"],
            ["git", "clean", "-fd"],
            ["docker", "rm", "-f"],
            ["docker", "rmi", "-f"],
        ]
        self._command_blocker.add_blocker(CommandBlocker.arguments_blocker(dangerous_subcommands))

    @classmethod
    def get_tool_info(cls) -> dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": "run_command",
            "display_name": "Run Command",
            "description": cls.__doc__,
        }

    def _validate_command(self) -> Optional[str]:
        """Validate command for security."""
        # Check for empty command
        if not self.command.strip():
            return "Empty command"

        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in self.command:
                return f"Potentially dangerous command pattern: {pattern}"

        # Parse command and check with blockers
        try:
            cmd_parts = shlex.split(self.command)
            block_reason = self._command_blocker.should_block(cmd_parts)
            if block_reason:
                return block_reason
        except ValueError as e:
            return f"Invalid command syntax: {e}"

        return None

    def _validate_working_directory(self, workspace_path: str) -> Optional[str]:
        """Validate working directory is within workspace."""
        if not self.cwd:
            return None

        try:
            cwd_abs = os.path.abspath(self.cwd)
            workspace_abs = os.path.abspath(workspace_path)

            # Check if cwd is within workspace
            if not cwd_abs.startswith(workspace_abs):
                return f"Working directory {self.cwd} is outside workspace"

            # Check if directory exists
            if not os.path.exists(cwd_abs):
                return f"Working directory {self.cwd} does not exist"

            if not os.path.isdir(cwd_abs):
                return f"Working directory {self.cwd} is not a directory"

        except Exception as e:
            return f"Invalid working directory: {e}"

        return None

    def execute(self, context: AgentContext) -> ToolResult:
        """Execute the command."""
        try:
            # Validate command first
            validation_error = self._validate_command()
            if validation_error:
                return ToolResult(success=False, data=None, error=validation_error)

            # Validate working directory
            working_dir = self.cwd
            if not working_dir:
                working_dir = str(context.workspace_path)

            dir_validation_error = self._validate_working_directory(str(context.workspace_path))
            if dir_validation_error:
                return ToolResult(success=False, data=None, error=dir_validation_error)

            # Parse command
            try:
                cmd_parts = shlex.split(self.command)
            except ValueError as e:
                return ToolResult(success=False, data=None, error=f"Invalid command syntax: {e}")

            # Execute command with timeout
            result = self._run_command_with_timeout(cmd_parts, working_dir)

            return ToolResult(
                success=(result["returncode"] == 0),
                data={
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "returncode": result["returncode"],
                    "command": self.command,
                    "cwd": working_dir,
                },
                error=None if result["returncode"] == 0 else f"Command failed with return code {result['returncode']}",
            )
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            return ToolResult(success=False, data=None, error=f"Error executing command: {e!s}\nTraceback:\n{tb}")

    def _run_command_with_timeout(self, cmd_parts: list[str], working_dir: str) -> dict[str, Any]:
        """Run command with timeout handling."""
        result = {"stdout": "", "stderr": "", "returncode": 1}

        def _handle_timeout() -> None:
            """Handle command timeout by killing the process."""
            process.terminate()
            thread.join(timeout=5)  # Give it 5 seconds to terminate gracefully
            if thread.is_alive():
                process.kill()  # Force kill if still alive

        def _raise_timeout() -> None:
            """Raise timeout exception."""
            raise subprocess.TimeoutExpired(cmd_parts, self.timeout)

        try:
            # Security: Only allow trusted commands that have been validated
            process = subprocess.Popen(  # noqa: S603
                cmd_parts,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_environment(),
            )

            # Use threading to handle timeout
            def target() -> None:
                try:
                    stdout, stderr = process.communicate()
                    result["stdout"] = stdout
                    result["stderr"] = stderr
                    result["returncode"] = process.returncode
                except Exception:
                    logfire.exception("Error executing command")

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=self.timeout)

            if thread.is_alive():
                # Command timed out, kill the process
                _handle_timeout()
                # Raise timeout exception
                _raise_timeout()

        except subprocess.TimeoutExpired:
            result["stderr"] = f"Command timed out after {self.timeout} seconds"
            result["returncode"] = -1
        except Exception as e:
            result["stderr"] = str(e)
            result["returncode"] = -1

        return result

    def _get_environment(self) -> dict[str, str]:
        """Get environment variables for command execution."""
        env = os.environ.copy()

        # Add some safety environment variables
        env["PATH"] = env.get("PATH", "")
        env["HOME"] = env.get("HOME", "")

        # Remove potentially dangerous environment variables
        dangerous_vars = ["SUDO_ASKPASS", "SSH_AUTH_SOCK", "SSH_AGENT_PID"]
        for var in dangerous_vars:
            env.pop(var, None)

        return env
