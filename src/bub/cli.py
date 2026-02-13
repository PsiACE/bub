"""Bub framework CLI bootstrap."""

from __future__ import annotations

from pathlib import Path

import typer

from bub.framework import BubFramework

app = typer.Typer(name="bub", help="Batteries-included, hook-first AI framework", add_completion=False)


def _load_cli_commands() -> None:
    framework = BubFramework(Path.cwd())
    framework.load_skills()
    framework.register_cli_commands(app)

    if not app.registered_commands:
        @app.command("help")
        def _help() -> None:
            typer.echo("No CLI command skills loaded. Install a command skill in .agent/skills.")


_load_cli_commands()
