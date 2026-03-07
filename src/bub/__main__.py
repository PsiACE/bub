"""Bub framework CLI bootstrap."""

from __future__ import annotations

import typer

from bub.framework import BubFramework


def create_cli_app() -> typer.Typer:
    framework = BubFramework()
    framework.load_hooks()
    app = framework.create_cli_app()

    if not app.registered_commands:

        @app.command("help")
        def _help() -> None:
            typer.echo("No CLI command loaded.")

    return app


app = create_cli_app()

if __name__ == "__main__":
    app()
