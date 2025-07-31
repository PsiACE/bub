"""CLI event definitions for the domain-driven event architecture."""

from typing import Any, Optional

from bub.events.models import BaseEvent
from bub.events.registry import register_event
from bub.events.types import DomainEventType

# ============================================================================
# CLI EVENT TYPES
# ============================================================================


class CLIEventType(DomainEventType):
    """CLI event types."""

    USER_INPUT = "cli.user_input"
    CHAT_STARTED = "cli.chat_started"
    CHAT_ENDED = "cli.chat_ended"
    COMMAND_EXECUTED = "cli.command_executed"
    ERROR_OCCURRED = "cli.error_occurred"
    MESSAGE_REQUESTED = "cli.message_requested"
    WELCOME_REQUESTED = "cli.welcome_requested"
    USAGE_INFO_REQUESTED = "cli.usage_info_requested"
    CONVERSATION_RESET_REQUESTED = "cli.conversation_reset_requested"
    DEBUG_TOGGLE_REQUESTED = "cli.debug_toggle_requested"


class UIEventType(DomainEventType):
    """UI event types."""

    MESSAGE_RENDERED = "ui.message_rendered"
    DEBUG_TOGGLED = "ui.debug_toggled"
    CONVERSATION_RESET = "ui.conversation_reset"
    USER_INPUT_RECEIVED = "ui.user_input_received"
    WELCOME_DISPLAYED = "ui.welcome_displayed"
    USAGE_INFO_DISPLAYED = "ui.usage_info_displayed"
    USER_INPUT_REQUESTED = "ui.user_input_requested"
    TAAO_MESSAGE_RENDERED = "ui.taao_message_rendered"


# ============================================================================
# CLI EVENTS (CLI domain publishes these)
# ============================================================================


@register_event
class UserInputEvent(BaseEvent):
    """Event emitted when user provides input."""

    event_type = CLIEventType.USER_INPUT

    input_text: str
    command: Optional[str] = None
    workspace_path: Optional[str] = None


@register_event
class ChatStartedEvent(BaseEvent):
    """Event emitted when chat session starts."""

    event_type = CLIEventType.CHAT_STARTED

    workspace_path: str
    model: str
    tools: list[str]


@register_event
class ChatEndedEvent(BaseEvent):
    """Event emitted when chat session ends."""

    event_type = CLIEventType.CHAT_ENDED

    reason: str


@register_event
class CommandExecutedEvent(BaseEvent):
    """Event emitted when a command is executed."""

    event_type = CLIEventType.COMMAND_EXECUTED

    command: str
    workspace_path: str
    model: str


@register_event
class ErrorOccurredEvent(BaseEvent):
    """Event emitted when an error occurs."""

    event_type = CLIEventType.ERROR_OCCURRED

    error_message: str
    error_type: str
    context: Optional[dict[str, Any]] = None


# ============================================================================
# CLI REQUEST EVENTS (CLI domain publishes these, UI domain subscribes)
# ============================================================================


@register_event
class CLIMessageRequestedEvent(BaseEvent):
    """Event emitted when CLI requests a message to be rendered."""

    event_type = CLIEventType.MESSAGE_REQUESTED

    message_type: str  # "info", "success", "error", "warning", "assistant"
    content: str


@register_event
class CLIWelcomeRequestedEvent(BaseEvent):
    """Event emitted when CLI requests welcome message."""

    event_type = CLIEventType.WELCOME_REQUESTED


@register_event
class CLIUsageInfoRequestedEvent(BaseEvent):
    """Event emitted when CLI requests usage info display."""

    event_type = CLIEventType.USAGE_INFO_REQUESTED

    workspace_path: str
    model: str
    tools: list[str]


@register_event
class CLIConversationResetRequestedEvent(BaseEvent):
    """Event emitted when CLI requests conversation reset."""

    event_type = CLIEventType.CONVERSATION_RESET_REQUESTED


@register_event
class CLIDebugToggleRequestedEvent(BaseEvent):
    """Event emitted when CLI requests debug toggle."""

    event_type = CLIEventType.DEBUG_TOGGLE_REQUESTED

    enabled: bool


# ============================================================================
# UI EVENTS (UI domain publishes these)
# ============================================================================


@register_event
class MessageRenderedEvent(BaseEvent):
    """Event emitted when a message is rendered."""

    event_type = UIEventType.MESSAGE_RENDERED

    message_type: str  # "info", "success", "error", "warning", "user", "assistant"
    content: str
    debug_mode: bool = False


@register_event
class DebugToggledEvent(BaseEvent):
    """Event emitted when debug mode is toggled."""

    event_type = UIEventType.DEBUG_TOGGLED

    enabled: bool


@register_event
class ConversationResetEvent(BaseEvent):
    """Event emitted when conversation is reset."""

    event_type = UIEventType.CONVERSATION_RESET


@register_event
class UserInputReceivedEvent(BaseEvent):
    """Event emitted when user input is received."""

    event_type = UIEventType.USER_INPUT_RECEIVED

    input_text: str
    debug_mode: bool = False


@register_event
class WelcomeDisplayedEvent(BaseEvent):
    """Event emitted when welcome message is displayed."""

    event_type = UIEventType.WELCOME_DISPLAYED

    message: str


@register_event
class UsageInfoDisplayedEvent(BaseEvent):
    """Event emitted when usage information is displayed."""

    event_type = UIEventType.USAGE_INFO_DISPLAYED

    workspace_path: Optional[str] = None
    model: str = ""
    tools: Optional[list[str]] = None


@register_event
class UserInputRequestedEvent(BaseEvent):
    """Event emitted when user input is requested."""

    event_type = UIEventType.USER_INPUT_REQUESTED

    prompt: str = "[bold cyan]You[/bold cyan]"


@register_event
class TAAOMessageRenderedEvent(BaseEvent):
    """Event emitted when TAAO process message is rendered."""

    event_type = UIEventType.TAAO_MESSAGE_RENDERED

    taao_type: str  # "thought", "action", "action_input", "observation"
    content: str
    debug_mode: bool
