"""Builtin CLI command hooks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer

from bub.envelope import field_of
from bub.framework import BubFramework
from bub.hookspecs import hookimpl


class CliCoreSkill:
    @hookimpl
    def register_cli_commands(self, app: typer.Typer) -> None:
        @app.command("run")
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

        @app.command("skills")
        def list_skills(
            workspace: Path | None = typer.Option(None, "--workspace", "-w"),  # noqa: B008
        ) -> None:
            """Show loaded and failed skills."""

            framework = _load_framework(workspace)
            for record in framework.loaded_skills:
                typer.echo(
                    f"loaded {record.skill.name} ({record.skill.source}) -> {record.skill.metadata.get('entrypoint')}"
                )
            for skill_name, error in framework.failed_skills.items():
                typer.echo(f"failed {skill_name}: {error}")

        @app.command("hooks")
        def list_hooks(
            workspace: Path | None = typer.Option(None, "--workspace", "-w"),  # noqa: B008
        ) -> None:
            """Show hook implementation mapping."""

            framework = _load_framework(workspace)
            report = framework.hook_report()
            if not report:
                typer.echo("(no hook implementations)")
                return
            for hook_name, plugins in report.items():
                typer.echo(f"{hook_name}: {', '.join(plugins)}")


plugin = CliCoreSkill()


def _load_framework(workspace: Path | None) -> BubFramework:
    resolved_workspace = (workspace or Path.cwd()).resolve()
    framework = BubFramework(resolved_workspace)
    framework.load_skills()
    return framework
