"""Shell and process-related tool factories."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from republic import Tool, tool_from_model

from ...agent.context import Context
from .shared import BashInput, BubInput


def create_bash_tool(context: Context) -> Tool:
    """Create the bash tool bound to the workspace context."""

    def _handler(params: BashInput) -> str:
        working_dir = params.cwd or str(context.workspace_path)
        bash_executable = shutil.which("bash") or "bash"
        try:
            # User intentionally runs shell commands through the bash tool.
            result = subprocess.run(  # noqa: S603
                [bash_executable, "-lc", params.cmd],
                cwd=working_dir,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"error: {exc!s}"

        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip()
        if result.returncode != 0:
            detail = output or "(empty)"
            return f"error: exit={result.returncode}\n{detail}"
        return output if output else "(empty)"

    return tool_from_model(
        BashInput,
        _handler,
        name="bash",
        description="Run a shell command",
    )


def create_bub_tool(render_notice: Callable[[list[str]], str]) -> Tool:
    """Create the bub command tool."""

    def _handler(params: BubInput) -> str:
        return str(render_notice(params.args or []))

    return tool_from_model(
        BubInput,
        _handler,
        name="bub",
        description="Show Bub session notice",
    )
