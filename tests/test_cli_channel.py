import json
from base64 import b64decode
from pathlib import Path

import pytest

from bub.channels.cli import CliChannel, CliInput, InlineImage


class _DummyRuntime:
    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = workspace or Path.cwd()

        class _Settings:
            model = "openrouter:test"

            @staticmethod
            def resolve_home() -> Path:
                return Path.cwd()

        self.settings = _Settings()

    def get_session(self, _session_id: str):
        class _Tape:
            @staticmethod
            def info():
                class _Info:
                    entries = 0
                    anchors = 0
                    last_anchor = None

                return _Info()

        class _Session:
            tape = _Tape()
            tool_view = type("_ToolView", (), {"all_tools": staticmethod(lambda: [])})()

        return _Session()


def test_normalize_input_keeps_agent_mode_text() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "agent"
    assert cli._normalize_input("echo hi") == "echo hi"


def test_normalize_input_adds_shell_prefix_in_shell_mode() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "shell"
    assert cli._normalize_input("echo hi") == ", echo hi"


def test_normalize_input_keeps_explicit_prefixes_in_shell_mode() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "shell"
    assert cli._normalize_input(",help") == ",help"
    assert cli._normalize_input(",ls -la") == ",ls -la"
    assert cli._normalize_input(", ls -la") == ", ls -la"


def test_cli_channel_disables_debounce() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    assert cli.debounce_enabled is False


def test_cli_channel_does_not_wrap_prompt() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    assert cli.format_prompt("plain prompt") == "plain prompt"


@pytest.mark.asyncio
async def test_get_session_prompt_without_images_returns_plain_text() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    session_id, prompt = await cli.get_session_prompt(CliInput(text="hello"))
    assert session_id == "cli"
    assert prompt == "hello"


def test_build_cli_input_extracts_local_image(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(
        b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z9xQAAAAASUVORK5CYII=")
    )
    cli = CliChannel(_DummyRuntime(tmp_path))  # type: ignore[arg-type]

    payload, notices = cli._build_cli_input(f"describe this @{image_path}")

    assert payload.text == "describe this"
    assert len(payload.images) == 1
    assert payload.images[0].path == str(image_path.resolve())
    assert payload.images[0].data_url.startswith("data:image/png;base64,")
    assert notices


def test_build_cli_input_extracts_clipboard_placeholder() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    cli._clipboard_images = {
        "abc.png": InlineImage(
            id="abc.png",
            data_url="data:image/png;base64,AAAA",
            mime_type="image/png",
            file_size=4,
            width=1,
            height=1,
        )
    }

    payload, _notices = cli._build_cli_input("look [image:abc.png,1x1] now")

    assert payload.text == "look  now"
    assert len(payload.images) == 1
    assert payload.images[0].id == "abc.png"


@pytest.mark.asyncio
async def test_get_session_prompt_with_images_uses_json_payload() -> None:
    cli = CliChannel(_DummyRuntime())  # type: ignore[arg-type]
    image = InlineImage(
        id="img.png",
        data_url="data:image/png;base64,AAAA",
        mime_type="image/png",
        file_size=4,
    )

    session_id, prompt = await cli.get_session_prompt(CliInput(text="look", images=(image,)))
    data = json.loads(prompt)

    assert session_id == "cli"
    assert data["message"] == "look"
    assert data["source"] == "cli"
    assert data["media"]["images"][0]["data_url"] == "data:image/png;base64,AAAA"
