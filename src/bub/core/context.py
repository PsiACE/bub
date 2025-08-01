"""Context for the agent package."""

from pathlib import Path
from typing import Any, Optional

from openai.types.chat import ChatCompletionMessageParam

from .prompt import DEFAULT_SYSTEM_PROMPT


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
        """
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.system_prompt = DEFAULT_SYSTEM_PROMPT + "\n" + (system_prompt or "")
        self.workspace_path = workspace_path or Path.cwd()
        self.tool_registry: Optional[Any] = None  # Will be set by Agent
        self._conversation_history: list[ChatCompletionMessageParam] = []

    def get_system_prompt(self) -> str:
        """Get the system prompt or default."""
        if self.system_prompt:
            return self.system_prompt
        return DEFAULT_SYSTEM_PROMPT

    def build_context_message(self) -> str:
        """Build a clean context message with essential information."""
        if not self.tool_registry:
            return f"[Environment Context]\nWorkspace: {self.workspace_path}\nNo tools available"

        tool_schemas = self.tool_registry.get_tool_schemas()
        available_tools = list(tool_schemas.keys())
        tool_details = self.tool_registry._format_schemas_for_context()

        msg = [
            "[Environment Context]",
            f"Workspace: {self.workspace_path}",
            f"Available tools ({len(available_tools)}): {', '.join(available_tools)}",
            "",
            "[Tool Definitions]",
            tool_details,
            "",
            "[Usage Instructions]",
            "To use a tool, provide the tool name and parameters in JSON format.",
            'Example: {"command": "ls -la"} for run_command tool',
        ]
        return "\n".join(msg)

    def reset(self) -> None:
        """Reset the context state."""
        self.reset_conversation()

    def compress(self, max_messages: int = 10) -> None:
        """Compress the conversation history."""
        self.compress_conversation(max_messages)

    def set_conversation_history(self, history: list[ChatCompletionMessageParam]) -> None:
        """Set the conversation history.

        Args:
            history: List of conversation messages
        """
        self._conversation_history = history

    def get_conversation_history(self) -> list[ChatCompletionMessageParam]:
        """Get the conversation history.

        Returns:
            List of conversation messages
        """
        return self._conversation_history

    def add_to_conversation_history(self, message: ChatCompletionMessageParam) -> None:
        """Add a message to the conversation history.

        Args:
            message: Message to add
        """
        self._conversation_history.append(message)

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self._conversation_history = []

    def compress_conversation(self, max_messages: int = 10) -> None:
        """Compress conversation history to keep only recent messages.

        Args:
            max_messages: Maximum number of messages to keep
        """
        if len(self._conversation_history) > max_messages:
            # Keep recent messages, prioritize keeping system message if any

            recent_messages = self._conversation_history[-max_messages:]
            self._conversation_history = recent_messages
