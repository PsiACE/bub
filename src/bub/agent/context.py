"""Context and message types for the agent package."""

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import get_settings


class Message(BaseModel):
    """A message in the conversation."""

    role: str = Field(..., description="Message role (user/assistant)")
    content: str = Field(..., description="Message content")


class Context:
    """Agent environment context: workspace, config, tool registry, etc."""

    def __init__(self, workspace_path: Optional[Path] = None, config: Optional[Any] = None):
        self.workspace_path = workspace_path or Path.cwd()
        self.config = config or get_settings()
        self.tool_registry = None  # Will be set by Agent

    def get_system_prompt(self) -> str:
        """Get the system prompt from config."""
        return self.config.system_prompt or ""

    def build_context_message(self) -> str:
        """Build a clean context message with essential information."""
        if not self.tool_registry:
            return f"[Environment Context]\nWorkspace: {self.workspace_path}\nNo tools available"

        tool_schemas = self.tool_registry.get_tool_schemas()
        msg = [
            "[Environment Context]",
            f"Workspace: {self.workspace_path}",
            f"Available tools: {', '.join(tool_schemas.keys())}",
            f"Tool schemas: {self.tool_registry._format_schemas_for_context()}",
        ]
        return "\n".join(msg)
