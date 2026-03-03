from pathlib import Path

from bub.channels.cli import CliChannel


class _DummyRuntime:
    def __init__(self) -> None:
        self.workspace = Path.cwd()

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
