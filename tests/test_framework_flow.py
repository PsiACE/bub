from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from bub.cli import app
from bub.framework import BubFramework


def _write_stateful_test_skill(workspace: Path) -> None:
    skill_dir = workspace / ".agent" / "skills" / "stateful-hooks"
    adapter_file = skill_dir / "agents" / "bub" / "adapter.py"
    adapter_file.parent.mkdir(parents=True)
    adapter_file.write_text("from fixtures_plugins.stateful_hooks import adapter\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: stateful-hooks",
                "description: test-only stateful hooks skill",
                "---",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_framework_processes_message_with_builtin_skills(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "local", "sender_id": "u1", "content": "hello framework"}
    )

    assert result.session_id == "stdout:local"
    assert "hello framework" in result.prompt
    assert result.model_output == "hello framework"
    assert result.outbounds
    assert result.outbounds[0]["content"] == result.model_output


@pytest.mark.asyncio
async def test_framework_increments_state_across_turns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_stateful_test_skill(tmp_path)
    monkeypatch.syspath_prepend(str(Path(__file__).parent))

    framework = BubFramework(tmp_path)
    framework.load_skills()

    first = await framework.process_inbound({"channel": "stdout", "chat_id": "same", "sender_id": "u1", "content": "first"})
    second = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "same", "sender_id": "u1", "content": "second"}
    )

    assert "turn=1" in first.model_output
    assert "turn=2" in second.model_output


@pytest.mark.asyncio
async def test_framework_accepts_user_defined_message_object(tmp_path: Path) -> None:
    class CustomMessage:
        def __init__(self, *, channel: str, chat_id: str, sender_id: str, content: str) -> None:
            self.channel = channel
            self.chat_id = chat_id
            self.sender_id = sender_id
            self.content = content

    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        CustomMessage(channel="stdout", chat_id="obj", sender_id="u1", content="object message")
    )

    assert result.session_id == "stdout:obj"
    assert "object message" in result.model_output


def test_framework_registers_cli_commands_from_skills(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()
    app = typer.Typer()

    framework.register_cli_commands(app)

    command_names = {command.name for command in app.registered_commands}
    assert {"run", "skills", "hooks"}.issubset(command_names)


def test_framework_reports_skill_statuses(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    states = {item.skill.name: item.state for item in framework.skill_statuses}
    assert states["cli"] == "hook_active"
    assert states["runtime"] == "hook_active"


def test_skills_command_shows_profile_column(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["skills", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "profile=" in result.stdout


@pytest.mark.asyncio
async def test_framework_routes_internal_command_with_runtime(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "local", "sender_id": "u1", "content": ",help"}
    )

    assert "Commands use ',' at line start." in result.model_output


@pytest.mark.asyncio
async def test_framework_routes_shell_command_with_runtime(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "local", "sender_id": "u1", "content": ",echo runtime-ok"}
    )

    assert "runtime-ok" in result.model_output


@pytest.mark.asyncio
async def test_runtime_normalizes_inbound_content(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "local", "sender_id": "u1", "content": "  padded message  "}
    )

    assert result.prompt == "padded message"


@pytest.mark.asyncio
async def test_runtime_resolve_session_ignores_blank_session_id(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {
            "channel": "stdout",
            "chat_id": "trim",
            "sender_id": "u1",
            "session_id": "   ",
            "content": "hello",
        }
    )

    assert result.session_id == "stdout:trim"
