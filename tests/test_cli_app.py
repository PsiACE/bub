import asyncio
import importlib
import signal
from pathlib import Path

import pytest
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
            telegram_allow_chats = ()

        self.settings = _Settings()
        self.registry = type("_Registry", (), {"descriptors": staticmethod(lambda: [])})()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = (exc_type, exc, tb)
        return None

    def set_bus(self, _bus) -> None:
        return None

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


def test_run_command_forwards_allowed_tools_and_skills(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, _session_id: str, _text: str):
            class _Result:
                error = None
                assistant_output = "ok"
                immediate_output = ""

            return _Result()

    def _fake_build_runtime(
        workspace: Path,
        *,
        model=None,
        max_tokens=None,
        allowed_tools=None,
        allowed_skills=None,
    ):
        captured["workspace"] = workspace
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        captured["allowed_tools"] = allowed_tools
        captured["allowed_skills"] = allowed_skills
        return _RunRuntime(workspace)

    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    runner = CliRunner()
    result = runner.invoke(
        cli_app_module.app,
        [
            "run",
            "ping",
            "--workspace",
            str(tmp_path),
            "--tools",
            "fs.read, web.search",
            "--tools",
            "bash",
            "--skills",
            "skill-a, skill-b",
        ],
    )

    assert result.exit_code == 0
    assert "ok" in result.output
    assert captured["workspace"] == tmp_path
    assert captured["allowed_tools"] == {"fs.read", "web.search", "bash"}
    assert captured["allowed_skills"] == {"skill-a", "skill-b"}


def test_run_command_uses_env_session_id_by_default(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, session_id: str, _text: str):
            captured["session_id"] = session_id

            class _Result:
                error = None
                assistant_output = "ok"
                immediate_output = ""

            return _Result()

    monkeypatch.setenv("BUB_SESSION_ID", "parent-session")
    monkeypatch.setattr(cli_app_module, "build_runtime", lambda workspace, **_: _RunRuntime(workspace))
    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["run", "ping", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert captured["session_id"] == "parent-session"


def test_run_command_session_id_option_overrides_env(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, session_id: str, _text: str):
            captured["session_id"] = session_id

            class _Result:
                error = None
                assistant_output = "ok"
                immediate_output = ""

            return _Result()

    monkeypatch.setenv("BUB_SESSION_ID", "parent-session")
    monkeypatch.setattr(cli_app_module, "build_runtime", lambda workspace, **_: _RunRuntime(workspace))
    runner = CliRunner()
    result = runner.invoke(
        cli_app_module.app,
        ["run", "ping", "--workspace", str(tmp_path), "--session-id", "explicit-session"],
    )

    assert result.exit_code == 0
    assert captured["session_id"] == "explicit-session"


@pytest.mark.asyncio
async def test_serve_channels_stops_manager_on_sigterm(monkeypatch) -> None:
    class _DummyRuntime:
        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel_active_inputs(self) -> int:
            self.cancel_calls += 1
            return 1

    class _DummyManager:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self._signal_handler = None
            self.runtime = _DummyRuntime()

        def enabled_channels(self):
            return {"telegram"}

        async def start(self) -> None:
            self.calls.append("start")

        async def stop(self) -> None:
            self.calls.append("stop")

    manager = _DummyManager()
    loop = asyncio.get_running_loop()
    original_add = loop.add_signal_handler
    original_remove = loop.remove_signal_handler

    def _add_signal_handler(sig, callback, *args):
        if sig == signal.SIGTERM:
            manager._signal_handler = callback
        return original_add(sig, callback, *args)

    def _remove_signal_handler(sig):
        return original_remove(sig)

    monkeypatch.setattr(loop, "add_signal_handler", _add_signal_handler)
    monkeypatch.setattr(loop, "remove_signal_handler", _remove_signal_handler)

    task = asyncio.create_task(cli_app_module._serve_channels(manager))
    await asyncio.sleep(0.05)
    assert manager.calls == ["start"]
    assert manager._signal_handler is not None

    manager._signal_handler()
    await asyncio.wait_for(task, timeout=1.0)

    assert manager.calls == ["start", "stop"]
    assert manager.runtime.cancel_calls == 1
