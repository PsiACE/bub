"""CLI main module for Bub."""

from __future__ import annotations

from pathlib import Path

import typer

from ..errors import ApiKeyNotConfiguredError, ConfigurationError
from ..runtime import Runtime
from .live import run_chat
from .render import create_cli_renderer

app = typer.Typer(
    name="bub",
    help="Bub it. Build it.",
    add_completion=False,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        chat()


renderer = create_cli_renderer()


def _build_runtime(
    workspace_path: Path,
    model: str | None,
    max_tokens: int | None,
) -> Runtime:
    try:
        return Runtime.build(workspace_path, model=model, max_tokens=max_tokens)
    except ApiKeyNotConfiguredError as exc:
        renderer.api_key_error()
        raise typer.Exit(1) from exc
    except ConfigurationError as exc:
        renderer.error(str(exc))
        raise typer.Exit(1) from exc


@app.command()
def chat(
    workspace: Path | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> None:
    """Start interactive chat with Bub."""
    try:
        workspace_path = workspace or Path.cwd()
        runtime = _build_runtime(workspace_path, model, max_tokens)

        renderer.welcome()
        renderer.usage_info(
            workspace_path=str(workspace_path),
            model=runtime.session.agent.model,
        )
        renderer.info("Type $help for commands.")
        renderer.info("Type $quit to end the session.")
        renderer.info("Type $debug to toggle tool trace visibility.")
        renderer.info("")

        run_chat(runtime, renderer)

    except Exception as exc:
        renderer.error(f"Failed to start chat: {exc!s}")
        raise typer.Exit(1) from exc


@app.command()
def run(
    command: str,
    workspace: Path | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> None:
    """Run a single command with Bub."""
    # Keep signature for CLI compatibility while run mode is intentionally disabled.
    _ = (command, workspace, model, max_tokens)
    renderer.error("bub run is not supported in async mode. Use bub chat.")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
