"""Typer CLI entrypoints."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from bub.app import build_runtime
from bub.channels import ChannelManager, MessageBus, TelegramChannel, TelegramConfig
from bub.cli.interactive import InteractiveCli
from bub.logging_utils import configure_logging

app = typer.Typer(name="bub", help="Tape-first coding agent CLI", add_completion=False)
TELEGRAM_DISABLED_ERROR = "telegram is disabled; set BUB_TELEGRAM_ENABLED=true"
TELEGRAM_TOKEN_ERROR = "missing telegram token; set BUB_TELEGRAM_TOKEN"  # noqa: S105


def _parse_subset(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None

    names: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            name = part.strip()
            if name:
                names.add(name)
    return names or None


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        chat()


@app.command()
def chat(
    workspace: Annotated[Path | None, typer.Option("--workspace", "-w")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
) -> None:
    """Run interactive CLI."""

    configure_logging(profile="chat")
    resolved_workspace = (workspace or Path.cwd()).resolve()
    logger.info(
        "chat.start workspace={} model={} max_tokens={}",
        str(resolved_workspace),
        model or "<default>",
        max_tokens if max_tokens is not None else "<default>",
    )
    runtime = build_runtime(resolved_workspace, model=model, max_tokens=max_tokens)
    cli = InteractiveCli(runtime)
    asyncio.run(cli.run())


@app.command()
def run(
    message: Annotated[str, typer.Argument()],
    workspace: Annotated[Path | None, typer.Option("--workspace", "-w")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
    session_id: Annotated[str, typer.Option("--session-id", envvar="BUB_SESSION_ID")] = "cli",
    tools: Annotated[
        list[str] | None,
        typer.Option(
            "--tools",
            help="Allowed tool names (repeatable or comma-separated, supports command and model names).",
        ),
    ] = None,
    skills: Annotated[
        list[str] | None,
        typer.Option(
            "--skills",
            help="Allowed skill names (repeatable or comma-separated).",
        ),
    ] = None,
) -> None:
    """Run a single message and exit, useful for quick testing or one-off commands."""
    import rich

    configure_logging(profile="chat")
    resolved_workspace = (workspace or Path.cwd()).resolve()
    allowed_tools = _parse_subset(tools)
    allowed_skills = _parse_subset(skills)
    logger.info(
        "run.start workspace={} model={} max_tokens={} allowed_tools={} allowed_skills={}",
        str(resolved_workspace),
        model or "<default>",
        max_tokens if max_tokens is not None else "<default>",
        ",".join(sorted(allowed_tools)) if allowed_tools else "<all>",
        ",".join(sorted(allowed_skills)) if allowed_skills else "<all>",
    )
    runtime = build_runtime(
        resolved_workspace,
        model=model,
        max_tokens=max_tokens,
        allowed_tools=allowed_tools,
        allowed_skills=allowed_skills,
    )
    result = asyncio.run(runtime.handle_input(session_id, message))
    if result.error:
        rich.print(f"[red]Error:[/red] {result.error}", file=sys.stderr)
    else:
        rich.print(result.assistant_output or result.immediate_output or "")


@app.command()
def telegram(
    workspace: Annotated[Path | None, typer.Option("--workspace", "-w")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
) -> None:
    """Run Telegram adapter with the same agent loop runtime."""

    configure_logging()
    resolved_workspace = (workspace or Path.cwd()).resolve()
    logger.info(
        "telegram.start workspace={} model={} max_tokens={}",
        str(resolved_workspace),
        model or "<default>",
        max_tokens if max_tokens is not None else "<default>",
    )

    with build_runtime(resolved_workspace, model=model, max_tokens=max_tokens) as runtime:
        token = runtime.settings.telegram_token
        if not runtime.settings.telegram_enabled:
            logger.error("telegram.disabled workspace={}", str(resolved_workspace))
            raise typer.BadParameter(TELEGRAM_DISABLED_ERROR)
        if not token:
            logger.error("telegram.missing_token workspace={}", str(resolved_workspace))
            raise typer.BadParameter(TELEGRAM_TOKEN_ERROR)

        bus = MessageBus()
        runtime.set_bus(bus)
        manager = ChannelManager(bus, runtime)
        manager.register(
            TelegramChannel(
                bus,
                TelegramConfig(
                    token=token,
                    allow_from=set(runtime.settings.telegram_allow_from),
                ),
            )
        )
        try:
            asyncio.run(_serve_channels(manager))
        except KeyboardInterrupt:
            logger.info("telegram.interrupted")
        except Exception:
            logger.exception("telegram.crash")
            raise
        finally:
            logger.info("telegram.stop workspace={}", str(resolved_workspace))


async def _serve_channels(manager: ChannelManager) -> None:
    channels = sorted(manager.enabled_channels())
    logger.info("channels.start enabled={}", channels)
    await manager.start()
    try:
        await asyncio.Event().wait()
    finally:
        await manager.stop()
        logger.info("channels.stop")


if __name__ == "__main__":
    app()
