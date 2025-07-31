"""Context for the agent package."""

from pathlib import Path
from typing import Any, Optional


class AgentContext:
    """Agent environment context: workspace, config, tool registry, etc."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str,
        api_base: Optional[str] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        workspace_path: Optional[Path] = None,
        config: Optional[Any] = None,
    ) -> None:
        """Initialize the agent context.

        Args:
            provider: LLM provider (e.g., 'openai', 'anthropic')
            model_name: Model name (e.g., 'gpt-4', 'claude-3')
            api_key: API key for the provider
            api_base: Optional API base URL
            max_tokens: Maximum tokens for responses
            system_prompt: System prompt for the agent
            workspace_path: Path to workspace
            config: Configuration object
        """
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path or Path.cwd()
        self.config = config
        self.tool_registry = None  # Will be set by Agent

    def get_system_prompt(self) -> str:
        """Get the system prompt from config or default."""
        if self.system_prompt:
            return self.system_prompt
        if self.config and hasattr(self.config, "system_prompt") and isinstance(self.config.system_prompt, str):
            return self.config.system_prompt
        return "You are a helpful AI assistant."

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

    def reset(self) -> None:
        """Reset the context state."""
        # Reset any conversation history or state
        pass
