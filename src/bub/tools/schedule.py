from __future__ import annotations

import subprocess
import sys

from loguru import logger

SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS = 300


def run_scheduled_reminder(message: str, session_id: str, workspace: str | None = None) -> None:
    if session_id.startswith("telegram:"):
        chat_id = session_id.split(":", 1)[1]
        message = (
            f"[Reminder for Telegram chat {chat_id}, after done, send a notice to this chat if necessary]\n{message}"
        )
    command = [sys.executable, "-m", "bub.cli.app", "run", "--session-id", session_id, message]

    logger.info("running scheduled reminder via bub run session_id={} message={}", session_id, message)
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            check=True,
            cwd=workspace,
            timeout=SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "scheduled reminder timed out after {}s session_id={}",
            SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS,
            session_id,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("scheduled reminder failed with exit={}", exc.returncode)
    else:
        logger.info("scheduled reminder succeeded with exit={}", completed.returncode)
