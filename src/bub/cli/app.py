"""CLI main module for Bub."""

from pathlib import Path
from typing import Any, Optional

import typer

from ..agent import Agent
from ..config import get_settings
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
        # Default to chat mode
        chat()


renderer = create_cli_renderer()


def _exit_with_error(message: str) -> None:
    """Exit with error message."""
    renderer.error(message)
    raise typer.Exit(1)


def _validate_workspace(workspace_path: Path) -> None:
    """Validate workspace directory exists."""
    if not workspace_path.exists():
        _exit_with_error(f"Workspace directory does not exist: {workspace_path}")


def _validate_api_key(settings: Any) -> None:
    """Validate API key is present."""
    if not settings.api_key:
        renderer.api_key_error()
        raise typer.Exit(1)


def _create_agent(settings: Any, workspace_path: Path, model: Optional[str], max_tokens: Optional[int]) -> Agent:
    """Create and return an Agent instance."""
    return Agent(
        api_key=settings.api_key,
        api_base=settings.api_base,
        model=model or settings.model,
        max_tokens=max_tokens or settings.max_tokens,
        workspace_path=workspace_path,
        system_prompt=settings.system_prompt,
    )


def _handle_special_commands(user_input: str, agent: Agent) -> Optional[bool]:
    cmd = user_input.lower()
    if cmd in ["quit", "exit", "q"]:
        renderer.info("Goodbye!")
        return True  # break
    elif cmd == "reset":
        agent.reset_conversation()
        renderer.conversation_reset()
        return False  # continue
    elif cmd == "debug":
        renderer.toggle_debug()
        return False  # continue
    return None  # not a special command


def _handle_chat_loop(agent: Agent) -> None:
    """Handle the interactive chat loop."""
    while True:
        try:
            user_input = renderer.get_user_input()
            if not user_input.strip():
                continue
            special = _handle_special_commands(user_input, agent)
            if special is True:
                break
            if special is False:
                continue

            def on_step(kind: str, content: str) -> None:
                if kind == "assistant":
                    renderer.assistant_message(content)
                elif kind == "observation":
                    # Pass observation through assistant_message to apply TAAO filtering
                    renderer.assistant_message(content)
                elif kind == "error":
                    renderer.error(content)

            agent.chat(user_input, on_step=on_step)
            renderer.info("")

        except (KeyboardInterrupt, EOFError):
            renderer.info("\nGoodbye!")
            break


@app.command()
def chat(
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """Start interactive chat with Bub."""
    try:
        settings = get_settings()
        _validate_api_key(settings)

        workspace_path = workspace or Path.cwd()
        _validate_workspace(workspace_path)

        agent = _create_agent(settings, workspace_path, model, max_tokens)

        renderer.welcome()
        renderer.usage_info(
            workspace_path=str(workspace_path),
            model=agent.model or "",  # ensure str
            tools=agent.tool_registry.list_tools(),
        )
        renderer.info("Type 'quit', 'exit', or 'q' to end the session.")
        renderer.info("Type 'reset' to clear conversation history.")
        renderer.info("Type 'debug' to toggle TAAO process visibility.")
        renderer.info("")

        _handle_chat_loop(agent)

    except Exception as e:
        renderer.error(f"Failed to start chat: {e!s}")
        raise typer.Exit(1) from e


@app.command()
def run(
    command: str,
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """Run a single command with Bub."""
    try:
        settings = get_settings()
        _validate_api_key(settings)

        workspace_path = workspace or Path.cwd()
        _validate_workspace(workspace_path)

        agent = _create_agent(settings, workspace_path, model, max_tokens)

        renderer.info(f"Executing: {command}")

        def on_step(kind: str, content: str) -> None:
            if kind == "assistant":
                renderer.assistant_message(content)
            elif kind == "observation":
                # Pass observation through assistant_message to apply TAAO filtering
                renderer.assistant_message(content)
            elif kind == "error":
                renderer.error(content)

        agent.chat(command, on_step=on_step)

    except Exception as e:
        renderer.error(f"Failed to execute command: {e!s}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
