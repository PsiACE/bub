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
    """Run a single request-response turn with Bub."""
    try:
        workspace_path = workspace or Path.cwd()
        runtime = _build_runtime(workspace_path, model, max_tokens)
        _run_once(runtime, command)
    except Exception as exc:
        renderer.error(f"Failed to run command: {exc!s}")
        raise typer.Exit(1) from exc


def _run_once(runtime: Runtime, command: str) -> None:
    route = runtime.session.handle_input(command, origin="human")
    if route.exit_requested or route.done_requested or not route.enter_agent:
        return

    response = runtime.session.agent_respond(
        on_event=lambda event: runtime.tape.record_tool_event(event.kind, event.payload)
    )
    assistant_result = runtime.session.interpret_assistant(response)
    if assistant_result.visible_text:
        runtime.tape.record_assistant_message(assistant_result.visible_text)
        renderer.info(assistant_result.visible_text)


if __name__ == "__main__":
    app()
