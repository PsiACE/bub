from __future__ import annotations

import subprocess
import sys

from loguru import logger


def run_scheduled_reminder(message: str, session_id: str) -> None:
    command = [sys.executable, "-m", "bub.cli.app", "run", "--session-id", session_id]
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
