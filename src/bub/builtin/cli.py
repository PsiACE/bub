"""Builtin CLI command adapter."""

# ruff: noqa: B008
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from bub.channels.message import ChannelMessage
from bub.envelope import field_of
from bub.framework import BubFramework

app = typer.Typer()


def _load_framework(workspace: Path | None) -> BubFramework:
    if workspace is None:
        workspace = Path.cwd()
    framework = BubFramework(workspace)
    framework.load_hooks()
    return framework


def run(
    message: str = typer.Argument(..., help="Inbound message content"),
    workspace: Path | None = typer.Option(None, "--workspace", "-w", help="Workspace root"),
    channel: str = typer.Option("cli", "--channel", help="Message channel"),
    chat_id: str = typer.Option("local", "--chat-id", help="Chat id"),
    sender_id: str = typer.Option("human", "--sender-id", help="Sender id"),
    session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
) -> None:
    """Run one inbound message through the framework pipeline."""

    framework = _load_framework(workspace)
    inbound = ChannelMessage(
        session_id=f"{channel}:{chat_id}" if session_id is None else session_id,
        content=message,
        channel=channel,
        chat_id=chat_id,
        context={"sender_id": sender_id},
    )

    result = asyncio.run(framework.process_inbound(inbound))
    for outbound in result.outbounds:
        rendered = str(field_of(outbound, "content", ""))
        target_channel = str(field_of(outbound, "channel", "stdout"))
        target_chat = str(field_of(outbound, "chat_id", "local"))
        typer.echo(f"[{target_channel}:{target_chat}]\n{rendered}")


def list_hooks(
    workspace: Path | None = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Show hook implementation mapping."""

    framework = _load_framework(workspace)
    report = framework.hook_report()
    if not report:
        typer.echo("(no hook implementations)")
        return
    for hook_name, adapter_names in report.items():
        typer.echo(f"{hook_name}: {', '.join(adapter_names)}")


def message(
    workspace: Path | None = typer.Option(None, "--workspace", "-w"),
    enable_channels: list[str] = typer.Option([], "--enable-channel", help="Channels to enable for CLI (default: all)"),
) -> None:
    """Start message listener(like telegram)."""
    from bub.channels.manager import ChannelManager

    framework = _load_framework(workspace)

    manager = ChannelManager(framework, enabled_channels=enable_channels or None)
    asyncio.run(manager.listen_and_run())


def chat(
    workspace: Path | None = typer.Option(None, "--workspace", "-w"),
    chat_id: str = typer.Option("local", "--chat-id", help="Chat id"),
    session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
) -> None:
    """Start a REPL chat session."""
    from bub.channels.manager import ChannelManager

    framework = _load_framework(workspace)

    manager = ChannelManager(framework, enabled_channels=["cli"])
    channel = manager.get_channel("cli")
    if channel is None:
        typer.echo("CLI channel not found. Please check your hook implementations.")
        raise typer.Exit(1)
    channel.set_metadata(chat_id=chat_id, session_id=session_id)  # type: ignore[attr-defined]
    asyncio.run(manager.listen_and_run())
