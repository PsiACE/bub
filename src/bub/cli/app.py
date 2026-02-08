"""Typer CLI entrypoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from bub.app import build_runtime
from bub.channels import ChannelManager, MessageBus, TelegramChannel, TelegramConfig
from bub.cli.interactive import InteractiveCli

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

    runtime = build_runtime(workspace or Path.cwd(), model=model, max_tokens=max_tokens)
    InteractiveCli(runtime).run()


@app.command()
def telegram(
    workspace: Annotated[Path | None, typer.Option("--workspace", "-w")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
) -> None:
    """Run Telegram adapter with the same agent loop runtime."""

    runtime = build_runtime(workspace or Path.cwd(), model=model, max_tokens=max_tokens)
    token = runtime.settings.telegram_token
    if not runtime.settings.telegram_enabled:
        raise typer.BadParameter(TELEGRAM_DISABLED_ERROR)
    if not token:
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
        return


async def _serve_channels(manager: ChannelManager) -> None:
    await manager.start()
    try:
        while True:
            await asyncio.sleep(1.0)
    finally:
        await manager.stop()
