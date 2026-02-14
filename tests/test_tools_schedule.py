import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bub.tools.schedule import SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS, run_scheduled_reminder


def test_run_scheduled_reminder_invokes_bub_run(monkeypatch: Any, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def _fake_run(command: list[str], **kwargs: Any) -> Any:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("bub.tools.schedule.subprocess.run", _fake_run)

    run_scheduled_reminder("remind me", "telegram:42")

    assert observed["command"] == [
        sys.executable,
        "-m",
        "bub.cli.app",
        "run",
        "--session-id",
        "telegram:42",
        "[Reminder for Telegram chat 42, after done, send a notice to this chat if necessary]\nremind me",
    ]
    assert observed["kwargs"] == {"check": True, "cwd": None, "timeout": SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS}


def test_run_scheduled_reminder_handles_timeout(monkeypatch: Any) -> None:
    def _fake_run(command: list[str], **kwargs: Any) -> Any:
        _ = kwargs
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr("bub.tools.schedule.subprocess.run", _fake_run)

    run_scheduled_reminder("remind me", "telegram:42")
