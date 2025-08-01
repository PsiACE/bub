"""CLI main module for Bub using domain-driven event architecture."""

from pathlib import Path
from typing import Callable, Optional

import typer

from bub.bridges.base import EventSystemDomainBridge
from bub.cli.domain import CLIDomain
from bub.cli.ui import UIDomain
from bub.config import Settings, get_settings, read_bubmd
from bub.core.agent import Agent

_settings = get_settings()

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


def _create_domains() -> tuple[CLIDomain, UIDomain]:
    """Create CLI and UI domains with event bridge."""
    bridge = EventSystemDomainBridge()
    cli_domain = CLIDomain(bridge)
    ui_domain = UIDomain(bridge)
    return cli_domain, ui_domain


def _exit_with_error() -> None:
    """Exit with error code."""
    raise typer.Exit(1)


def _create_agent(
    settings: Settings, workspace_path: Path, model_override: Optional[str], max_tokens: Optional[int]
) -> Agent:
    """Create and return an Agent instance."""
    # Parse model override if provided (format: provider/model or just model)
    if model_override:
        if "/" in model_override:
            provider, model_name = model_override.split("/", 1)
        else:
            provider = settings.provider or "openai"
            model_name = model_override
    else:
        provider = settings.provider or "openai"
        model_name = settings.model_name or "gpt-3.5-turbo"

    system_prompt = (
        settings.system_prompt + "\n" + read_bubmd(workspace_path)
        if settings.system_prompt
        else read_bubmd(workspace_path)
    )

    return Agent(
        provider=provider,
        model_name=model_name,
        api_key=settings.api_key or "",
        api_base=settings.api_base,
        max_tokens=max_tokens or settings.max_tokens,
        workspace_path=workspace_path,
        system_prompt=system_prompt,
        config=get_settings(workspace_path),
        timeout_seconds=settings.timeout_seconds,
        max_iterations=settings.max_iterations,
    )


def _handle_special_commands(user_input: str, agent: Agent, cli_domain: CLIDomain) -> Optional[bool]:
    """Handle special commands through CLI domain events."""
    cmd = user_input.lower()
    if cmd in ["quit", "exit", "q"]:
        # Publish quit command event - UI will handle the display
        cli_domain.handle_user_input(user_input, command="quit")
        cli_domain.end_chat("user_exit")
        return True  # break
    elif cmd == "reset":
        agent.reset_conversation()
        # Publish reset command event - UI will handle the display
        cli_domain.handle_user_input(user_input, command="reset")
        cli_domain.publish_conversation_reset()
        return False  # continue
    elif cmd == "debug":
        # Publish debug command event - UI will handle the toggle
        cli_domain.handle_user_input(user_input, command="debug")
        cli_domain.toggle_debug_mode()
        return False  # continue
    return None  # not a special command


def _create_step_handler(cli_domain: CLIDomain) -> Callable[[str, str], None]:
    """Create a step handler function for the agent."""

    def on_step(kind: str, content: str) -> None:
        # Publish step events through CLI domain
        if kind == "assistant":
            cli_domain.publish_assistant_message(content)
        elif kind == "observation":
            cli_domain.publish_observation_message(content)
        elif kind == "error":
            cli_domain.publish_error_message(content)
        elif kind == "taao_thought":
            cli_domain.publish_taao_message("thought", content)
        elif kind == "taao_action":
            cli_domain.publish_taao_message("action", content)
        elif kind == "taao_action_input":
            cli_domain.publish_taao_message("action_input", content)
        elif kind == "taao_observation":
            cli_domain.publish_taao_message("observation", content)

    return on_step


def _handle_chat_loop(agent: Agent, cli_domain: CLIDomain, ui_domain: UIDomain) -> None:
    """Handle the interactive chat loop using direct method calls."""
    while True:
        try:
            # Get user input through UI domain
            user_input = ui_domain.get_user_input()
            if not user_input.strip():
                continue

            special = _handle_special_commands(user_input, agent, cli_domain)
            if special is True:
                break
            if special is False:
                continue

            # Handle user input through CLI domain
            cli_domain.handle_user_input(user_input)

            # Create step handler and execute agent chat
            on_step = _create_step_handler(cli_domain)
            try:
                agent.chat(user_input, on_step=on_step, debug_mode=cli_domain.debug_mode)
                cli_domain.publish_info_message("")
            except Exception as e:
                # Handle agent-specific errors
                error_msg = f"Agent error: {e!s}"
                cli_domain.publish_error_message(error_msg)
                cli_domain.handle_error(error_msg, "agent_error", {"exception_type": type(e).__name__})

        except (KeyboardInterrupt, EOFError):
            cli_domain.publish_info_message("\nGoodbye!")
            cli_domain.end_chat("keyboard_interrupt")
            break
        except Exception as e:
            # Handle unexpected errors in the chat loop
            error_msg = f"Unexpected error in chat loop: {e!s}"
            cli_domain.publish_error_message(error_msg)
            cli_domain.handle_error(error_msg, "chat_loop_error", {"exception_type": type(e).__name__})
            # Continue the loop instead of breaking to allow recovery
            continue


@app.command()
def chat(
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """Start interactive chat with Bub."""
    try:
        # Create domains
        cli_domain, ui_domain = _create_domains()

        workspace_path = workspace or Path.cwd()

        # Validate workspace through CLI domain
        if not cli_domain.validate_workspace(workspace_path):
            _exit_with_error()

        settings = get_settings(workspace_path)

        # Validate configuration through CLI domain
        if not cli_domain.validate_api_key(settings.api_key):
            _exit_with_error()
        if not cli_domain.validate_model_config(settings.provider, settings.model_name):
            _exit_with_error()

        agent = _create_agent(settings, workspace_path, model, max_tokens)

        # Start chat session through CLI domain
        cli_domain.start_chat(
            workspace_path=workspace_path,
            model=agent.model or "",
            tools=agent.tool_registry.list_tools(),
        )

        # Display UI through CLI domain events
        cli_domain.publish_welcome_message()
        cli_domain.publish_usage_info(
            workspace_path=str(workspace_path),
            model=agent.model or "",
            tools=agent.tool_registry.list_tools(),
        )

        _handle_chat_loop(agent, cli_domain, ui_domain)

    except Exception as e:
        # Create domains for error handling if not already created
        try:
            cli_domain, ui_domain = _create_domains()
        except Exception:
            # Fallback to basic error handling
            raise typer.Exit(1) from e

        cli_domain.publish_error_message(f"Failed to start chat: {e!s}")
        cli_domain.handle_error(
            f"Failed to start chat: {e!s}",
            "startup_error",
            {"exception_type": type(e).__name__},
        )
        raise typer.Exit(1) from e


def _setup_run_environment(
    workspace: Optional[Path], model: Optional[str], max_tokens: Optional[int]
) -> tuple[Agent, CLIDomain, UIDomain]:
    """Setup environment for run command."""
    cli_domain, ui_domain = _create_domains()
    workspace_path = workspace or Path.cwd()

    if not cli_domain.validate_workspace(workspace_path):
        _exit_with_error()

    settings = get_settings(workspace_path)

    if not cli_domain.validate_api_key(settings.api_key):
        _exit_with_error()
    if not cli_domain.validate_model_config(settings.provider, settings.model_name):
        _exit_with_error()

    agent = _create_agent(settings, workspace_path, model, max_tokens)
    return agent, cli_domain, ui_domain


@app.command()
def run(
    command: str,
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """Run a single command with Bub."""
    try:
        agent, cli_domain, ui_domain = _setup_run_environment(workspace, model, max_tokens)

        # Execute command through CLI domain
        cli_domain.execute_command(command)
        cli_domain.publish_info_message(f"Executing: {command}")

        # Create step handler and execute agent chat
        on_step = _create_step_handler(cli_domain)
        agent.chat(command, on_step=on_step, debug_mode=cli_domain.debug_mode)

    except Exception as e:
        # Create domains for error handling if not already created
        try:
            cli_domain, ui_domain = _create_domains()
        except Exception:
            # Fallback to basic error handling
            raise typer.Exit(1) from e

        cli_domain.publish_error_message(f"Failed to execute command: {e!s}")
        cli_domain.handle_error(
            f"Failed to execute command: {e!s}",
            "execution_error",
            {"command": command, "exception_type": type(e).__name__},
        )
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
