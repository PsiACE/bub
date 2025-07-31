"""UI domain using the bridge pattern for event-driven architecture."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from bub.bridges.base import BaseDomain, DomainEventBridge

from .events import (
    CLIEventType,
    ConversationResetEvent,
    DebugToggledEvent,
    MessageRenderedEvent,
    UIEventType,
    UserInputReceivedEvent,
)


class UIDomain(BaseDomain):
    """UI domain that manages rendering and user interaction."""

    def __init__(self, bridge: DomainEventBridge) -> None:
        """Initialize UI domain.

        Args:
            bridge: Event bridge for communication
        """
        super().__init__(bridge, "ui")
        self._console = Console(markup=True, highlight=True)
        self._prompt = Prompt()
        self._debug_mode: bool = False
        self._conversation_count: int = 0

    def _setup_subscriptions(self) -> None:
        """Setup event subscriptions for UI domain."""
        # Subscribe to CLI events to react to state changes
        self.subscribe(CLIEventType.CHAT_STARTED, self._handle_chat_started)
        self.subscribe(CLIEventType.USER_INPUT, self._handle_user_input)
        self.subscribe(CLIEventType.COMMAND_EXECUTED, self._handle_command_executed)
        self.subscribe(CLIEventType.ERROR_OCCURRED, self._handle_error_occurred)

        # Subscribe to CLI message requests (CLI domain publishes these)
        self.subscribe(CLIEventType.MESSAGE_REQUESTED, self._handle_message_requested)
        self.subscribe(CLIEventType.WELCOME_REQUESTED, self._handle_welcome_requested)
        self.subscribe(CLIEventType.USAGE_INFO_REQUESTED, self._handle_usage_info_requested)
        self.subscribe(CLIEventType.CONVERSATION_RESET_REQUESTED, self._handle_conversation_reset_requested)
        self.subscribe(CLIEventType.DEBUG_TOGGLE_REQUESTED, self._handle_debug_toggle_requested)
        self.subscribe(UIEventType.USER_INPUT_REQUESTED, self._handle_user_input_requested)

    def _handle_chat_started(self, event: Any) -> None:
        """Handle chat started event."""
        pass

    def _handle_user_input(self, event: Any) -> None:
        """Handle user input event."""
        pass

    def _handle_command_executed(self, event: Any) -> None:
        """Handle command executed event."""
        pass

    def _handle_error_occurred(self, event: Any) -> None:
        """Handle error occurred event."""
        pass

    def _handle_message_rendered(self, event: Any) -> None:
        """Handle message rendered event."""
        message_type = getattr(event, "message_type", "info")
        content = getattr(event, "content", "")
        _debug_mode = getattr(event, "debug_mode", False)

        self.render(message_type, content=content)

    def _handle_welcome_displayed(self, event: Any) -> None:
        """Handle welcome displayed event."""
        message = getattr(event, "message", "Welcome to Bub!")
        self._console.print("[bold blue]" + message + "[/bold blue]")

    def _handle_usage_info_displayed(self, event: Any) -> None:
        """Handle usage info displayed event."""
        workspace_path = getattr(event, "workspace_path", "")
        model = getattr(event, "model", "")
        tools = getattr(event, "tools", [])

        self._console.print(f"[dim]Workspace:[/dim] {workspace_path}")
        self._console.print(f"[dim]Model:[/dim] {model}")
        self._console.print(f"[dim]Tools:[/dim] {', '.join(tools) if tools else 'None'}")

    def _handle_conversation_reset(self, event: Any) -> None:
        """Handle conversation reset event."""
        self._conversation_count = 0
        self._console.print("[yellow]Conversation history cleared.[/yellow]")

    def _handle_debug_toggled(self, event: Any) -> None:
        """Handle debug toggle event."""
        enabled = getattr(event, "enabled", False)
        self._debug_mode = enabled
        status = "enabled" if enabled else "disabled"
        self._console.print(f"[yellow]Debug mode {status}.[/yellow]")

    def _handle_message_requested(self, event: Any) -> None:
        """Handle message requested event."""
        event_data = event.data
        message_type = event_data.get("message_type", "info")
        content = event_data.get("content", "")

        self.render(message_type, content=content)

    def _handle_welcome_requested(self, event: Any) -> None:
        """Handle welcome requested event."""
        self._render_welcome_panel()

    def _handle_usage_info_requested(self, event: Any) -> None:
        """Handle usage info requested event."""
        event_data = event.data
        workspace_path = event_data.get("workspace_path", "")
        model = event_data.get("model", "")
        tools = event_data.get("tools", [])

        self._render_usage_info(workspace_path, model, tools)

    def _handle_conversation_reset_requested(self, event: Any) -> None:
        """Handle conversation reset requested event."""
        self.conversation_reset()

    def _handle_debug_toggle_requested(self, event: Any) -> None:
        """Handle debug toggle requested event."""
        event_data = event.data
        enabled = event_data.get("enabled", False)
        self._debug_mode = enabled

        # Display the status change
        status = "enabled" if enabled else "disabled"
        status_color = "green" if enabled else "red"
        self._console.print(f"[{status_color}]Debug mode {status}.[/{status_color}]")

    def _handle_user_input_requested(self, event: Any) -> None:
        """Handle user input requested event."""
        event_data = event.data
        prompt = event_data.get("prompt", "[bold cyan]You[/bold cyan]")
        self._console.print(f"\n{prompt}: ", end="")

    def _publish_message_event(self, message_type: str, content: str, **kwargs: Any) -> None:
        """Publish message rendered event."""
        self.publish(
            MessageRenderedEvent(
                message_type=message_type,
                content=content,
                debug_mode=self._debug_mode,
            )
        )

    def render(self, event_type: str, **kwargs: Any) -> None:
        """Render event based on type."""
        if event_type == "info":
            self._render_info(kwargs.get("content", ""))
        elif event_type == "success":
            self._render_success(kwargs.get("content", ""))
        elif event_type == "error":
            self._render_error(kwargs.get("content", ""))
        elif event_type == "warning":
            self._render_warning(kwargs.get("content", ""))
        elif event_type == "assistant":
            self._render_assistant_message(kwargs.get("content", ""))
        elif event_type == "observation":
            self._render_observation_message(kwargs.get("content", ""))
        elif event_type.startswith("taao_"):
            taao_type = event_type.replace("taao_", "")
            self._render_react_step(taao_type, kwargs.get("content", ""))
        else:
            self._render_generic(event_type, kwargs)

    def _render_info(self, content: str) -> None:
        """Render info message with improved styling."""
        if content.strip():
            self._console.print(f"[blue]INFO:[/blue] {content}")

    def _render_success(self, content: str) -> None:
        """Render success message with improved styling."""
        if content.strip():
            self._console.print(f"[green]SUCCESS:[/green] {content}")

    def _render_error(self, content: str) -> None:
        """Render error message with improved styling."""
        if content.strip():
            self._console.print(f"[red]ERROR:[/red] {content}")

    def _render_warning(self, content: str) -> None:
        """Render warning message with improved styling."""
        if content.strip():
            self._console.print(f"[yellow]WARNING:[/yellow] {content}")

    def _render_assistant_message(self, content: str) -> None:
        """Render assistant message with enhanced styling."""
        # Increment conversation count for better UX
        self._conversation_count += 1

        # Create a panel for the assistant message
        assistant_text = Text(content, style="white")
        panel = Panel(
            assistant_text,
            title="[bold green]Bub[/bold green]",
            title_align="left",
            border_style="green",
            padding=(1, 2),
            highlight=True,
        )
        self._console.print(panel)

    def _render_observation_message(self, content: str) -> None:
        """Render observation message with improved styling."""
        if content.strip():
            self._console.print(f"[dim]OBSERVATION:[/dim] [dim]{content}[/dim]")

    def _render_react_step(self, step_type: str, content: str) -> None:
        """Render ReAct step with subtle styling for debug mode."""
        if not self._debug_mode:
            return

        # Define subtle colors and titles for different step types
        step_config = {
            "thought": {"color": "blue", "title": "THOUGHT", "style": "dim"},
            "action": {"color": "yellow", "title": "ACTION", "style": "dim"},
            "action_input": {"color": "dim", "title": "INPUT", "style": "dim"},
            "observation": {"color": "green", "title": "OBSERVATION", "style": "dim"},
        }

        config = step_config.get(step_type, {"color": "white", "title": step_type.upper(), "style": "dim"})

        # Use simple text instead of panels for debug steps to make them less prominent
        self._console.print(
            f"[{config['color']}]{config['title']}:[/{config['color']}] [{config['style']}]{content.strip()}[/{config['style']}]"
        )

    def _render_generic(self, event_type: str, kwargs: dict[str, Any]) -> None:
        """Render generic event."""
        content = kwargs.get("content", str(kwargs))
        self._console.print(f"[white]{event_type}:[/white] {content}")

    def _render_welcome_panel(self) -> None:
        """Render welcome panel with enhanced design."""
        # Create a beautiful banner with slogan
        banner_text = Text(
            "╭─ Bub ──────────────────────────────────────────────────────────────────────────────────────────────╮",
            style="bold cyan",
        )
        slogan_text = Text(
            "│                                                                                                          │",
            style="cyan",
        )
        title_text = Text(
            "│                                  Bub it. Build it.                                                      │",
            style="bold white",
        )
        subtitle_text = Text(
            "│                                  Your AI-powered assistant                                               │",
            style="dim white",
        )
        bottom_text = Text(
            "│                                                                                                          │",
            style="cyan",
        )
        footer_text = Text(
            "╰──────────────────────────────────────────────────────────────────────────────────────────────────────────╯",
            style="bold cyan",
        )

        # Print the banner
        self._console.print(banner_text)
        self._console.print(slogan_text)
        self._console.print(title_text)
        self._console.print(subtitle_text)
        self._console.print(bottom_text)
        self._console.print(footer_text)
        self._console.print("")

    def _render_usage_info(self, workspace_path: str, model: str, tools: list[str]) -> None:
        """Render usage information with enhanced design."""
        # Create a table for better organization
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="dim", width=12)
        table.add_column("Value", style="white")

        table.add_row("Workspace", workspace_path)
        table.add_row("Model", model)
        table.add_row("Tools", ", ".join(tools) if tools else "None")

        self._console.print(table)

        # Add elegant commands section
        self._console.print("")
        self._console.print("[bold cyan]Quick Commands:[/bold cyan]")

        # Create a compact commands table
        commands_table = Table(show_header=False, box=None, padding=(0, 2))
        commands_table.add_column("Command", style="bold green", width=12)
        commands_table.add_column("Description", style="dim")

        commands_table.add_row("quit/exit/q", "End the session")
        commands_table.add_row("reset", "Clear conversation history")
        commands_table.add_row("debug", "Toggle ReAct process visibility")

        self._console.print(commands_table)
        self._console.print("")

    def get_user_input(self) -> str:
        """Get user input from prompt with enhanced styling."""
        try:
            # Create a styled prompt
            prompt_text = Text("You", style="bold green")
            user_input = self._prompt.ask(prompt_text)

            if user_input.strip():
                self.publish(
                    UserInputReceivedEvent(
                        input_text=user_input,
                        debug_mode=self._debug_mode,
                    )
                )
        except (KeyboardInterrupt, EOFError):
            return "quit"
        else:
            return user_input

    def assistant_message(self, content: str) -> None:
        """Display assistant message."""
        self.render("assistant", content=content)

    def conversation_reset(self) -> None:
        """Handle conversation reset with enhanced feedback."""
        self._conversation_count = 0
        self._console.print(Rule("[yellow]Conversation Reset[/yellow]", style="yellow"))
        self.publish(ConversationResetEvent())

    def toggle_debug(self) -> None:
        """Toggle debug mode with enhanced feedback."""
        self._debug_mode = not self._debug_mode
        status = "enabled" if self._debug_mode else "disabled"
        status_color = "green" if self._debug_mode else "red"

        self._console.print(f"[{status_color}]Debug mode {status}.[/{status_color}]")
        self.publish(DebugToggledEvent(enabled=self._debug_mode))

    def info(self, content: str) -> None:
        """Display info message."""
        self._render_info(content)

    def error(self, content: str) -> None:
        """Display error message."""
        self._render_error(content)

    def success(self, content: str) -> None:
        """Display success message."""
        self._render_success(content)

    def warning(self, content: str) -> None:
        """Display warning message."""
        self._render_warning(content)

    @property
    def debug_mode(self) -> bool:
        """Get debug mode status."""
        return self._debug_mode

    @property
    def console(self) -> Console:
        """Get console instance."""
        return self._console
