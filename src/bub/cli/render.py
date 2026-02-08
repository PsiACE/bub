"""CLI rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


@dataclass
class CliRenderer:
    """Rich-based renderer for interactive CLI."""

    console: Console

    def welcome(self, *, model: str, workspace: str) -> None:
        body = (
            f"workspace: {workspace}\n"
            f"model: {model}\n"
            "internal command prefix: ','\n"
            "type ',help' for command list"
        )
        self.console.print(Panel(body, title="Bub", border_style="cyan"))

    def info(self, text: str) -> None:
        if not text.strip():
            return
        self.console.print(Text(text, style="bright_black"))

    def command_output(self, text: str) -> None:
        if not text.strip():
            return
        self.console.print(Panel(text, title="Command", border_style="green"))

    def assistant_output(self, text: str) -> None:
        if not text.strip():
            return
        self.console.print(Panel(text, title="Assistant", border_style="blue"))

    def error(self, text: str) -> None:
        if not text.strip():
            return
        self.console.print(Panel(text, title="Error", border_style="red"))
