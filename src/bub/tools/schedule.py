from __future__ import annotations

import subprocess
import sys

from loguru import logger


def run_scheduled_reminder(message: str, session_id: str, workspace: str | None = None) -> None:
    if session_id.startswith("telegram:"):
        chat_id = session_id.split(":", 1)[1]
        message = (
            f"[Reminder for Telegram chat {chat_id}, after done, send a notice to this chat if necessary]\n{message}"
        )
    command = [sys.executable, "-m", "bub.cli.app", "run", "--session-id", session_id]
    if workspace:
        command.extend(["--workspace", workspace])
    command.append(message)

    logger.info("running scheduled reminder via bub run session_id={} message={}", session_id, message)
    completed = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        logger.error(
            "scheduled reminder failed exit={} stderr={} stdout={}",
            completed.returncode,
            (completed.stderr or "").strip(),
            (completed.stdout or "").strip(),
        )
