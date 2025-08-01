"""CLI domain using the bridge pattern for event-driven architecture."""

from pathlib import Path
from typing import Any, Optional

from bub.events.bridges import BaseDomain, DomainEventBridge

from .events import (
    ChatEndedEvent,
    ChatStartedEvent,
    CLIConversationResetRequestedEvent,
    CLIDebugToggleRequestedEvent,
    CLIMessageRequestedEvent,
    CLIUsageInfoRequestedEvent,
    CLIWelcomeRequestedEvent,
    CommandExecutedEvent,
    ErrorOccurredEvent,
    UIEventType,
    UserInputEvent,
    UserInputRequestedEvent,
)


class CLIDomain(BaseDomain):
    """CLI domain that manages CLI state and events."""

    # Error messages
    NO_WORKSPACE_ERROR = "No workspace set"

    def __init__(self, bridge: DomainEventBridge) -> None:
        """Initialize CLI domain.

        Args:
            bridge: Event bridge for communication
        """
        super().__init__(bridge, "cli")
        self._current_workspace: Optional[Path] = None
        self._current_model: Optional[str] = None
        self._current_tools: list[str] = []
        self._chat_active: bool = False
        self._debug_mode: bool = False

    def _setup_subscriptions(self) -> None:
        """Setup event subscriptions for CLI domain."""
        # Subscribe to UI events that affect CLI state
        self.subscribe(UIEventType.DEBUG_TOGGLED, self._handle_debug_toggled)
        self.subscribe(UIEventType.CONVERSATION_RESET, self._handle_conversation_reset)
        self.subscribe(UIEventType.USER_INPUT_RECEIVED, self._handle_user_input_received)

    def _handle_debug_toggled(self, event: Any) -> None:
        """Handle debug mode toggle event."""
        self._debug_mode = getattr(event, "enabled", False)
        self.update_state({"debug_mode": self._debug_mode})

    def _handle_conversation_reset(self, event: Any) -> None:
        """Handle conversation reset event."""
        self._chat_active = False
        self.update_state({"chat_active": False})

    def _handle_user_input_received(self, event: Any) -> None:
        """Handle user input received event."""
        # Store the user input for retrieval
        input_text = getattr(event, "input_text", "")
        self.update_state({"last_user_input": input_text})

    def start_chat(self, workspace_path: Path, model: str, tools: list[str]) -> None:
        """Start a chat session."""
        self._current_workspace = workspace_path
        self._current_model = model
        self._current_tools = tools
        self._chat_active = True

        self.update_state({
            "workspace_path": str(workspace_path),
            "model": model,
            "tools": tools,
            "chat_active": True,
        })

        # Publish chat started event
        self.publish(
            ChatStartedEvent(
                workspace_path=str(workspace_path),
                model=model,
                tools=tools,
            )
        )

    def end_chat(self, reason: str = "user_exit") -> None:
        """End the current chat session."""
        self._chat_active = False
        self.update_state({"chat_active": False})

        # Publish chat ended event
        self.publish(ChatEndedEvent(reason=reason))

    def handle_user_input(self, input_text: str, command: Optional[str] = None) -> None:
        """Handle user input."""
        # Publish user input event
        self.publish(
            UserInputEvent(
                input_text=input_text,
                command=command,
                workspace_path=str(self._current_workspace) if self._current_workspace else None,
            )
        )

    def request_user_input(self) -> str:
        """Request user input through UI domain."""
        # Publish user input request event
        self.publish(UserInputRequestedEvent())

        # Fallback to direct prompt since UI domain access is not working
        from rich.prompt import Prompt

        return Prompt.ask("[bold green]You[/bold green]")

    def execute_command(self, command: str) -> None:
        """Execute a command."""
        if not self._current_workspace:
            raise ValueError(self.NO_WORKSPACE_ERROR)

        # Publish command executed event
        self.publish(
            CommandExecutedEvent(
                command=command,
                workspace_path=str(self._current_workspace),
                model=self._current_model or "unknown",
            )
        )

    def handle_error(self, error_message: str, error_type: str, context: Optional[dict[str, Any]] = None) -> None:
        """Handle an error occurrence."""
        # Publish error occurred event
        self.publish(
            ErrorOccurredEvent(
                error_message=error_message,
                error_type=error_type,
                context=context,
            )
        )

    # UI Message Publishing Methods
    def publish_info_message(self, content: str) -> None:
        """Publish info message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="info",
                content=content,
            )
        )

    def publish_error_message(self, content: str) -> None:
        """Publish error message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="error",
                content=content,
            )
        )

    def publish_success_message(self, content: str) -> None:
        """Publish success message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="success",
                content=content,
            )
        )

    def publish_warning_message(self, content: str) -> None:
        """Publish warning message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="warning",
                content=content,
            )
        )

    def publish_assistant_message(self, content: str) -> None:
        """Publish assistant message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="assistant",
                content=content,
            )
        )

    def publish_observation_message(self, content: str) -> None:
        """Publish observation message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type="observation",
                content=content,
            )
        )

    def publish_taao_message(self, taao_type: str, content: str) -> None:
        """Publish TAAO message request event."""
        self.publish(
            CLIMessageRequestedEvent(
                message_type=f"taao_{taao_type}",
                content=content,
            )
        )

    def publish_welcome_message(self) -> None:
        """Publish welcome message request event."""
        self.publish(CLIWelcomeRequestedEvent())

    def publish_usage_info(self, workspace_path: str, model: str, tools: list[str]) -> None:
        """Publish usage info request event."""
        self.publish(
            CLIUsageInfoRequestedEvent(
                workspace_path=workspace_path,
                model=model,
                tools=tools,
            )
        )

    def publish_conversation_reset(self) -> None:
        """Publish conversation reset request event."""
        self.publish(CLIConversationResetRequestedEvent())

    def publish_debug_toggle(self, enabled: bool) -> None:
        """Publish debug toggle request event."""
        self.publish(CLIDebugToggleRequestedEvent(enabled=enabled))

    def toggle_debug_mode(self) -> None:
        """Toggle debug mode and publish event."""
        self._debug_mode = not self._debug_mode
        self.update_state({"debug_mode": self._debug_mode})
        self.publish_debug_toggle(self._debug_mode)

    def validate_workspace(self, workspace_path: Path) -> bool:
        """Validate workspace directory exists."""
        if not workspace_path.exists():
            self.handle_error(
                f"Workspace directory does not exist: {workspace_path}",
                "validation_error",
                {"workspace_path": str(workspace_path)},
            )
            return False
        return True

    def validate_api_key(self, api_key: Optional[str]) -> bool:
        """Validate API key is present."""
        if not api_key:
            self.handle_error(
                "API key not found",
                "configuration_error",
                {"missing": "api_key"},
            )
            return False
        return True

    def validate_model_config(self, provider: Optional[str], model_name: Optional[str]) -> bool:
        """Validate provider and model configuration."""
        if not provider:
            self.handle_error(
                "Provider not configured. Set BUB_PROVIDER (e.g., 'openai', 'anthropic', 'ollama')",
                "configuration_error",
                {"missing": "provider"},
            )
            return False
        if not model_name:
            self.handle_error(
                "Model name not configured. Set BUB_MODEL_NAME (e.g., 'gpt-4', 'claude-3', 'llama2')",
                "configuration_error",
                {"missing": "model_name"},
            )
            return False
        return True

    @property
    def current_workspace(self) -> Optional[Path]:
        """Get current workspace path."""
        return self._current_workspace

    @property
    def current_model(self) -> Optional[str]:
        """Get current model name."""
        return self._current_model

    @property
    def current_tools(self) -> list[str]:
        """Get current tools list."""
        return self._current_tools.copy()

    @property
    def chat_active(self) -> bool:
        """Check if chat is currently active."""
        return self._chat_active

    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled."""
        return self._debug_mode
