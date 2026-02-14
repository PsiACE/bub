import asyncio
import contextlib
import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bub.core.agent_loop import LoopResult

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

    @contextlib.asynccontextmanager
    async def graceful_shutdown(self):
        stop_event = asyncio.Event()
        yield stop_event


def test_chat_command_invokes_interactive_runner(monkeypatch, tmp_path: Path) -> None:
    called = {"run": False}

    def _fake_build_runtime(workspace: Path, *, model=None, max_tokens=None, enable_scheduler=True):
        assert workspace == tmp_path
        assert enable_scheduler is True
        return DummyRuntime(workspace)

    class _FakeInteractive:
        def __init__(self, _runtime, session_id: str = "cli"):
            assert session_id == "cli"

        async def run(self) -> None:
            called["run"] = True

    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    monkeypatch.setattr(cli_app_module, "InteractiveCli", _FakeInteractive)

    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["chat", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert called["run"] is True


def test_message_command_requires_valid_subcommand_name(monkeypatch, tmp_path: Path) -> None:
    def _fake_build_runtime(workspace: Path, *, model=None, max_tokens=None):
        return DummyRuntime(workspace)

    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["telegram", "--workspace", str(tmp_path)])
    assert result.exit_code != 0
    assert "No such command 'telegram'" in result.output


def test_run_command_forwards_allowed_tools_and_skills(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, _session_id: str, _text: str):
            return LoopResult(
                immediate_output="",
                assistant_output="ok",
                exit_requested=False,
                steps=1,
                error=None,
            )

    def _fake_build_runtime(
        workspace: Path,
        *,
        model=None,
        max_tokens=None,
        allowed_tools=None,
        allowed_skills=None,
        enable_scheduler=True,
    ):
        captured["workspace"] = workspace
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        captured["allowed_tools"] = allowed_tools
        captured["allowed_skills"] = allowed_skills
        captured["enable_scheduler"] = enable_scheduler
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
    assert captured["enable_scheduler"] is True


def test_run_command_uses_env_session_id_by_default(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, session_id: str, _text: str):
            captured["session_id"] = session_id
            return LoopResult(
                immediate_output="",
                assistant_output="ok",
                exit_requested=False,
                steps=1,
                error=None,
            )

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
            return LoopResult(
                immediate_output="",
                assistant_output="ok",
                exit_requested=False,
                steps=1,
                error=None,
            )

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
            self.stop_event: asyncio.Event | None = None

        @contextlib.asynccontextmanager
        async def graceful_shutdown(self):
            stop_event = asyncio.Event()
            self.stop_event = stop_event
            yield stop_event

    class _DummyManager:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.runtime = _DummyRuntime()

        async def run(self) -> None:
            self.calls.append("start")
            try:
                await asyncio.Event().wait()
            finally:
                self.calls.append("stop")

    manager = _DummyManager()

    task = asyncio.create_task(cli_app_module._serve_channels(manager))
    await asyncio.sleep(0.05)
    assert manager.calls == ["start"]
    assert manager.runtime.stop_event is not None
    manager.runtime.stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert manager.calls == ["start", "stop"]
