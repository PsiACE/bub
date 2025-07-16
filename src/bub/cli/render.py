"""CLI renderer for Bub."""

import re
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt


class Renderer:
    """CLI renderer using Rich for beautiful terminal output."""

    def __init__(self) -> None:
        self.console: Console = Console()
        self._show_debug: bool = False

    def toggle_debug(self) -> None:
        """Toggle debug mode to show/hide TAAO process."""
        self._show_debug = not self._show_debug
        status = "enabled" if self._show_debug else "disabled"
        self.console.print(f"[dim]🔧 Debug mode {status}[/dim]")

    def info(self, message: str) -> None:
        """Render an info message."""
        self.console.print(message)

    def success(self, message: str) -> None:
        """Render a success message."""
        self.console.print(f"[green]{message}[/green]")

    def error(self, message: str) -> None:
        """Render an error message."""
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def warning(self, message: str) -> None:
        """Render a warning message."""
        self.console.print(f"[yellow]{message}[/yellow]")

    def welcome(self, message: str = "[bold blue]Bub[/bold blue] - Bub it. Build it.") -> None:
        """Render welcome message."""
        self.console.print(message)

    def usage_info(self, workspace_path: Optional[str] = None, model: str = "", tools: Optional[list] = None) -> None:
        """Render usage information."""
        if workspace_path:
            from ..tools.utils import sanitize_path

            display_path = sanitize_path(workspace_path)
            self.console.print(f"[bold]Working directory:[/bold] [cyan]{display_path}[/cyan]")
        if model:
            self.console.print(f"[bold]Model:[/bold] [magenta]{model}[/magenta]")
        if tools:
            self.console.print(f"[bold]Available tools:[/bold] [green]{', '.join(tools)}[/green]")

    def user_message(self, message: str) -> None:
        """Render user message."""
        self.console.print(f"[bold cyan]You:[/bold cyan] {message}")

    def assistant_message(self, message: str) -> None:
        """Render assistant message with smart formatting."""
        # Check if this is a TAAO process message
        if self._is_taao_message(message):
            if self._show_debug:
                self._render_taao_message(message)
            else:
                self._render_taao_minimal(message)
            return

        # Check if this is a final answer
        if self._is_final_answer(message):
            self._render_final_answer(message)
            return

        # Regular assistant message
        self.console.print(f"[bold yellow]Bub:[/bold yellow] {message}")

    def _is_taao_message(self, message: str) -> bool:
        """Check if message is part of TAAO process."""
        taao_patterns = [
            r"Thought:",
            r"Action:",
            r"Action Input:",
            r"Observation:",
        ]
        return any(re.search(pattern, message, re.IGNORECASE) for pattern in taao_patterns)

    def _is_final_answer(self, message: str) -> bool:
        """Check if message is a final answer."""
        return re.search(r"Final Answer:", message, re.IGNORECASE) is not None

    def _render_taao_message(self, message: str) -> None:
        """Render TAAO process message in debug mode."""
        if "Thought:" in message:
            self.console.print(f"[dim]💭 {message}[/dim]")
        elif "Action:" in message:
            self.console.print(f"[dim]🔧 {message}[/dim]")
        elif "Action Input:" in message:
            self.console.print(f"[dim]📝 {message}[/dim]")
        elif "Observation:" in message:
            # Make Observation even more subtle in debug mode
            # Extract just the key information from observation
            if "Output:" in message:
                output_match = re.search(r"Output:\s*(.+)", message, re.DOTALL)
                if output_match:
                    output = output_match.group(1).strip()
                    self.console.print(f"[dim]👁️  Output: {output}[/dim]")
                else:
                    self.console.print(f"[dim]👁️  {message}[/dim]")
            elif "Error:" in message:
                error_match = re.search(r"Error:\s*(.+)", message, re.DOTALL)
                if error_match:
                    error = error_match.group(1).strip()
                    self.console.print(f"[dim]👁️  Error: {error}[/dim]")
                else:
                    self.console.print(f"[dim]👁️  {message}[/dim]")
            else:
                self.console.print(f"[dim]👁️  {message}[/dim]")
        else:
            self.console.print(f"[dim]{message}[/dim]")

    def _render_taao_minimal(self, message: str) -> None:
        """Render minimal TAAO process message in normal mode."""
        # In normal mode, only show Action, hide everything else
        if "Action:" in message:
            action_match = re.search(r"Action:\s*(.+)", message, re.IGNORECASE)
            if action_match:
                action = action_match.group(1).strip()
                self.console.print(f"[dim]🔧 {action}[/dim]")
        # Hide Thought, Action Input, and Observation in normal mode

    def _render_final_answer(self, message: str) -> None:
        """Render final answer in a natural way."""
        # Extract the actual answer content
        match = re.search(r"Final Answer:\s*(.+)", message, re.IGNORECASE | re.DOTALL)
        if match:
            answer = match.group(1).strip()

            # Clean up common redundant phrases
            answer = re.sub(r"^The (command|output) .*? (was|is):\s*", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"^The result is:\s*", "", answer, flags=re.IGNORECASE)
            answer = re.sub(
                r"^The .*? executed successfully and produced the output:\s*", "", answer, flags=re.IGNORECASE
            )
            answer = re.sub(
                r"^The .*? command was executed, and it displayed the output:\s*", "", answer, flags=re.IGNORECASE
            )
            answer = re.sub(
                r"^The .*? command has been executed again, and the output is:\s*", "", answer, flags=re.IGNORECASE
            )
            answer = re.sub(
                r"^The .*? command was executed successfully, and it displayed the output:\s*",
                "",
                answer,
                flags=re.IGNORECASE,
            )

            # Remove backticks and extra formatting
            answer = re.sub(r"`([^`]+)`", r"\1", answer)

            if answer and answer.strip():
                self.console.print(f"[bold yellow]Bub:[/bold yellow] {answer}")
            else:
                self.console.print("[bold yellow]Bub:[/bold yellow] Done!")
        else:
            # Fallback to original message
            self.console.print(f"[bold yellow]Bub:[/bold yellow] {message}")

    def conversation_reset(self) -> None:
        """Render conversation reset message."""
        self.console.print("[green]Conversation history cleared.[/green]")

    def api_key_error(self) -> None:
        """Render API key error with helpful information."""
        self.error("API key not found")
        self.console.print("")
        self.info("Quick fix:")
        self.console.print('  export BUB_API_KEY="your-key-here"')
        self.console.print("")
        self.info("Get API keys from:")
        self.console.print("  - Anthropic: https://console.anthropic.com/")
        self.console.print("  - OpenAI: https://platform.openai.com/")
        self.console.print("  - Google: https://aistudio.google.com/")

    def get_user_input(self, prompt: str = "[bold cyan]You[/bold cyan]") -> str:
        """Get user input with styled prompt."""
        return Prompt.ask(prompt)


def create_cli_renderer() -> Renderer:
    """Create a CLI renderer."""
    return Renderer()


def get_user_input(prompt: str = "[bold cyan]You[/bold cyan]") -> str:
    """Get user input with styled prompt."""
    return Prompt.ask(prompt)
