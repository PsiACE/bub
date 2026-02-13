from __future__ import annotations

from pathlib import Path

import pytest
import typer

from bub.framework import BubFramework


@pytest.mark.asyncio
async def test_framework_processes_message_with_builtin_skills(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound(
        {"channel": "stdout", "chat_id": "local", "sender_id": "u1", "content": "hello framework"}
    )

    assert result.session_id == "stdout:local"
    assert "hello framework" in result.prompt
    assert result.model_output.startswith("[stdout:local] turn=1")
    assert result.outbounds
    assert result.outbounds[0]["content"] == result.model_output


@pytest.mark.asyncio
async def test_framework_increments_state_across_turns(tmp_path: Path) -> None:
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
