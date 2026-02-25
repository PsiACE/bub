"""Builtin CLI command adapter."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import typer

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
    workspace: Path | None = typer.Option(None, "--workspace", "-w", help="Workspace root"),  # noqa: B008
    channel: str = typer.Option("stdout", "--channel", help="Message channel"),
    chat_id: str = typer.Option("local", "--chat-id", help="Chat id"),
    sender_id: str = typer.Option("human", "--sender-id", help="Sender id"),
    session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
) -> None:
    """Run one inbound message through the framework pipeline."""

    framework = _load_framework(workspace)
    inbound: dict[str, Any] = {
        "channel": channel,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": message,
    }
    if session_id is not None and session_id.strip():
        inbound["session_id"] = session_id.strip()

    result = asyncio.run(framework.process_inbound(inbound))
    for outbound in result.outbounds:
        rendered = str(field_of(outbound, "content", ""))
        target_channel = str(field_of(outbound, "channel", "stdout"))
        target_chat = str(field_of(outbound, "chat_id", "local"))
        typer.echo(f"[{target_channel}:{target_chat}] {rendered}")


def list_hooks(
    workspace: Path | None = typer.Option(None, "--workspace", "-w"),  # noqa: B008
) -> None:
    """Show hook implementation mapping."""

    framework = _load_framework(workspace)
    report = framework.hook_report()
    if not report:
        typer.echo("(no hook implementations)")
        return
    for hook_name, adapter_names in report.items():
        typer.echo(f"{hook_name}: {', '.join(adapter_names)}")


def install_plugin(
    plugin_spec: str = typer.Argument(..., help="Python requirement string or github owner/repo"),
) -> None:
    """Install a plugin from PyPI or GitHub repository."""
    if "/" in plugin_spec and not plugin_spec.startswith("git+") and "github.com" not in plugin_spec:
        plugin_spec = f"git+https://github.com/{plugin_spec}.git"
    if uv_bin := _find_uv():
        typer.echo(f"Installing plugin '{plugin_spec}' with uv...")
        subprocess.run([uv_bin, "pip", "install", plugin_spec], check=True)  # noqa: S603
        return
    typer.echo(f"Installing plugin '{plugin_spec}' with pip...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-p", sys.executable, plugin_spec], check=True)  # noqa: S603


def _find_uv() -> Path | None:
    """Find uv executable in the system."""

    this_path = sysconfig.get_path("scripts")
    path_str = os.getenv("PATH", "")

    uv_path = shutil.which("uv", path=f"{this_path}{os.pathsep}{path_str}")
    if uv_path is not None:
        return Path(uv_path)
    return None
