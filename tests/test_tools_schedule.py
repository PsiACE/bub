import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bub.tools.schedule import run_scheduled_reminder


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
        "remind me",
    ]
    assert observed["kwargs"] == {"capture_output": True, "text": True, "check": False}
