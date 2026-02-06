"""CLI renderer for Bub."""

from rich.console import Console
from rich.prompt import Prompt


class Renderer:
    """CLI renderer using Rich for terminal output."""

    def __init__(self) -> None:
        self.console: Console = Console()
        self._show_debug: bool = False

    def toggle_debug(self) -> None:
        """Toggle debug mode to show/hide tool traces."""
        self._show_debug = not self._show_debug
        status = "enabled" if self._show_debug else "disabled"
        self.console.print(f"[dim]Debug mode {status}[/dim]")

    @property
    def show_debug(self) -> bool:
        """Expose debug toggle for callers."""
        return self._show_debug

    def info(self, message: str) -> None:
        """Render an info message."""
        self.console.print(message)

    def error(self, message: str) -> None:
        """Render an error message."""
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def welcome(self, message: str = "[bold blue]Bub[/bold blue] - Bub it. Build it.") -> None:
        """Render welcome message."""
        self.console.print(message)

    def usage_info(
        self,
        workspace_path: str | None = None,
        model: str = "",
        tools: list[str] | None = None,
    ) -> None:
        """Render usage information."""
        if workspace_path:
            self.console.print(f"[bold]Working directory:[/bold] [cyan]{workspace_path}[/cyan]")
        if model:
            self.console.print(f"[bold]Model:[/bold] [magenta]{model}[/magenta]")
        if tools:
            self.console.print(f"[bold]Available tools:[/bold] [green]{', '.join(tools)}[/green]")

    def user_message(self, message: str) -> None:
        """Render user message."""
        self.console.print(f"[bold cyan]You:[/bold cyan] {message}")

    def assistant_message(self, message: str) -> None:
        """Render assistant message."""
        self.console.print(f"[bold yellow]Bub:[/bold yellow] {message}")

    def action_result(self, title: str, status: str, stdout: str, stderr: str) -> None:
        """Render an action execution result."""
        header = title
        self.console.print(f"[dim]{header}[/dim]")
        if status == "ok":
            if stdout.strip():
                self.console.print(stdout.rstrip())
            else:
                self.console.print("[dim](no output)[/dim]")
            return
        if stderr.strip():
            self.console.print(f"[red]{stderr.rstrip()}[/red]")
        else:
            self.console.print("[red]command failed[/red]")

    def debug_message(self, message: str) -> None:
        """Render a debug message."""
        self.console.print(f"[dim]{message}[/dim]")

    def get_user_input(self) -> str:
        """Prompt user for input."""
        return Prompt.ask("[bold cyan]$[/bold cyan]")

    def api_key_error(self) -> None:
        """Display API key error message."""
        self.error("API key not configured. Set BUB_API_KEY in your environment or .env file.")


def create_cli_renderer() -> Renderer:
    """Create and return a Renderer instance."""
    return Renderer()
