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
        # Echo is always handled via events; no separate echo toggle
        self._view_mode: str = "conversation"  # conversation | process
        self._last_tick: object | None = None

    def toggle_debug(self) -> None:
        """Toggle debug mode to show/hide TAAO process."""
        self._show_debug = not self._show_debug
        status = "enabled" if self._show_debug else "disabled"
        self.console.print(f"[dim]Debug mode {status}[/dim]")

    def set_view_mode(self, mode: str) -> None:
        allowed = {"conversation", "process"}
        if mode not in allowed:
            self.console.print(f"[yellow]Unknown view mode '{mode}'. Allowed: conversation, process, raw[/yellow]")
            return
        self._view_mode = mode
        # No per-call prints to avoid noise; debug toggle announces mode

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
        """Render assistant message. Kept for compatibility; events drive UI normally."""
        if self._is_final_answer(message):
            self._render_final_answer(message)
            return
        self.console.print(f"[bold yellow]Bub:[/bold yellow] {message}")

    def render_event(self, event: object) -> None:
        """Render events from the agent bus in selected view mode."""
        etype = getattr(event, "type", "")
        data = getattr(event, "data", {})
        tick = getattr(event, "tick", "-")

        if self._view_mode == "process" and tick != self._last_tick:
            self._last_tick = tick
            self.console.print(f"[dim]— Tick {tick} —[/dim]")

        if self._view_mode == "conversation":
            self._render_conversation_event(etype, data)
            return
        if self._view_mode == "process":
            self._render_process_event(etype, data, tick)
            return
        # conversation mode handled above

    def _render_conversation_event(self, etype: str, data: dict) -> None:
        if etype == "user.input":
            msg = str(data.get("message", ""))
            self.user_message(msg)
            return
        if etype == "agent.thought":
            content = str(data.get("content", ""))
            # Minimal: only show Action line (dim)
            action_match = re.search(r"Action:\s*(.+)", content, re.IGNORECASE)
            if action_match:
                self.console.print(f"[dim]Action: {action_match.group(1).strip()}[/dim]")
            return
        if etype == "agent.observation":
            result = data.get("result")
            duration_ms = data.get("duration_ms")
            text = self._summarize_observation(result)
            if duration_ms is not None:
                text = f"{text} ({int(duration_ms)} ms)"
            # Minimal observation line (dim)
            self.console.print(f"[dim]{text}[/dim]")
            return
        if etype == "agent.final":
            content = str(data.get("content", ""))
            self._render_final_answer("Final Answer: " + content)
            return
        if etype == "agent.reset":
            self.conversation_reset()
            return

    def _render_process_event(self, etype: str, data: dict, tick: object) -> None:
        handler_name = "_process_" + etype.replace(".", "_")
        handler = getattr(self, handler_name, None)
        if callable(handler):
            handler(data)
        else:
            self.console.print(f"[dim]{etype} -> {data}[/dim]")

    def _process_user_input(self, data: dict) -> None:
        # In process view, show human input as You for clarity
        self.user_message(str(data.get("message", "")))

    def _process_agent_thought(self, data: dict) -> None:
        content = str(data.get("content", ""))
        for line in content.splitlines():
            if not line.strip():
                continue
            self.console.print("[dim]agent.thought: " + line + "[/dim]")

    def _process_agent_action(self, data: dict) -> None:
        tool = data.get("tool")
        params = data.get("input")
        self.console.print(f"[dim]agent.action: tool={tool} input={params}[/dim]")

    def _process_agent_action_started(self, data: dict) -> None:
        tool = data.get("tool")
        self.console.print(f"[dim]agent.action.started: {tool}[/dim]")

    def _process_agent_observation(self, data: dict) -> None:
        result = data.get("result")
        duration_ms = data.get("duration_ms")
        text = f"{result}" if result is not None else "<empty>"
        if duration_ms is not None:
            text = f"{text} ({int(duration_ms)} ms)"
        self.console.print(f"[dim]agent.observation: {text}[/dim]")

    def _process_agent_final(self, data: dict) -> None:
        content = str(data.get("content", ""))
        self._render_final_answer("Final Answer: " + content)

    def _process_agent_reset(self, data: dict) -> None:
        self.console.print("[dim]agent.reset: done[/dim]")

    # raw mode removed for consistency

    def _summarize_observation(self, result: object) -> str:
        # Conversation mode summarization
        if not isinstance(result, dict):
            return "Observation: Done" if result is not None else "Observation: <empty>"
        success = result.get("success")
        err = result.get("error")
        payload = result.get("data")
        if not success and err:
            return f"Observation: Error: {err}"
        if isinstance(payload, dict):
            stdout = str(payload.get("stdout", "")).strip()
            stderr = str(payload.get("stderr", "")).strip()
            if stdout:
                first = stdout.splitlines()[0]
                return f"Observation: Output: {first}"
            if stderr:
                first = stderr.splitlines()[0]
                return f"Observation: Error: {first}"
        return "Observation: Done"

    def _is_final_answer(self, message: str) -> bool:
        """Check if message is a final answer."""
        return re.search(r"Final Answer:", message, re.IGNORECASE) is not None

    def _render_final_answer(self, message: str) -> None:
        """Render final answer in a natural way."""
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

    def get_user_input(self, prompt: str = "> ") -> str:
        """Get user input with styled prompt."""
        return Prompt.ask(prompt)


def create_cli_renderer() -> Renderer:
    """Create a CLI renderer."""
    return Renderer()


def get_user_input(prompt: str = "> ") -> str:
    """Get user input with styled prompt."""
    return Prompt.ask(prompt)
