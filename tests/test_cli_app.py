import importlib
from pathlib import Path

from typer.testing import CliRunner

cli_app_module = importlib.import_module("bub.cli.app")


class DummyRuntime:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

        class _Settings:
            model = "openrouter:test"
            telegram_enabled = False
            telegram_token = None
            telegram_allow_from = ()

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

        return _Session()

    def handle_input(self, _session_id: str, _text: str):
        raise AssertionError


def test_chat_command_invokes_interactive_runner(monkeypatch, tmp_path: Path) -> None:
    called = {"run": False}

    def _fake_build_runtime(workspace: Path, *, model=None, max_tokens=None):
        assert workspace == tmp_path
        return DummyRuntime(workspace)

    class _FakeInteractive:
        def __init__(self, _runtime):
            pass

        async def run(self) -> None:
            called["run"] = True

    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    monkeypatch.setattr(cli_app_module, "InteractiveCli", _FakeInteractive)

    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["chat", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert called["run"] is True


def test_telegram_command_validates_enabled(monkeypatch, tmp_path: Path) -> None:
    def _fake_build_runtime(workspace: Path, *, model=None, max_tokens=None):
        return DummyRuntime(workspace)

    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["telegram", "--workspace", str(tmp_path)])
    assert result.exit_code != 0
    assert "telegram is disabled" in result.output
