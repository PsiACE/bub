"""Typer CLI entrypoints."""

from __future__ import annotations

import asyncio
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
    InteractiveCli(runtime).run()


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

    runtime = build_runtime(resolved_workspace, model=model, max_tokens=max_tokens)
    token = runtime.settings.telegram_token
    if not runtime.settings.telegram_enabled:
        logger.error("telegram.disabled workspace={}", str(resolved_workspace))
        raise typer.BadParameter(TELEGRAM_DISABLED_ERROR)
    if not token:
        logger.error("telegram.missing_token workspace={}", str(resolved_workspace))
        raise typer.BadParameter(TELEGRAM_TOKEN_ERROR)

    bus = MessageBus()
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
        while True:
            await asyncio.sleep(1.0)
    finally:
        await manager.stop()
        logger.info("channels.stop")
