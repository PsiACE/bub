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


def test_run_command_expands_home_in_workspace(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Path] = {}

    class _RunRuntime(DummyRuntime):
        async def handle_input(self, _session_id: str, _text: str):
            class _Result:
                error = None
                assistant_output = "ok"
                immediate_output = ""

            return _Result()

    def _fake_build_runtime(workspace: Path, **_kwargs):
        captured["workspace"] = workspace
        return _RunRuntime(workspace)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    expected_workspace = (fake_home / "workspace").resolve()

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(cli_app_module, "build_runtime", _fake_build_runtime)
    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["run", "ping", "--workspace", "~/workspace"])

    assert result.exit_code == 0
    assert captured["workspace"] == expected_workspace


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
