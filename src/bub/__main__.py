"""Bub framework CLI bootstrap."""

from __future__ import annotations

from pathlib import Path

import typer

from bub.framework import BubFramework


def create_cli_app() -> typer.Typer:
    app = typer.Typer(name="bub", help="Batteries-included, hook-first AI framework", add_completion=False)
    framework = BubFramework(Path.cwd())
    framework.load_hooks()
    framework.register_cli_commands(app)

    if not app.registered_commands:

        @app.command("help")
        def _help() -> None:
            typer.echo("No CLI command skills loaded. Install a command skill in .agent/skills.")

    return app


app = create_cli_app()

if __name__ == "__main__":
    app()
