"""Runtime logging helpers."""

from __future__ import annotations

import os
import sys
from logging import Handler
from typing import Literal

import loguru
from loguru import logger
from rich import get_console
from rich.logging import RichHandler

LogProfile = Literal["default", "chat"]

_PROFILE_FORMATS: dict[LogProfile, str] = {
    "chat": "{level} | {extra[tape]} |{message}",
    "default": "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<6} | {name}:{function}:{line} | {extra[tape]} | {message}",
}
_CONFIGURED_PROFILE: LogProfile | None = None


def _build_chat_handler() -> Handler:
    return RichHandler(
        console=get_console(),
        show_level=True,
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=False,
    )


def configure_logging(*, profile: LogProfile = "default") -> None:
    """Configure process-level logging once."""
    from bub.tape.service import current_tape

    def inject_context(record: loguru.Record) -> None:
        record["extra"]["tape"] = current_tape()

    global _CONFIGURED_PROFILE
    if profile == _CONFIGURED_PROFILE:
        return

    level = os.getenv("BUB_LOG_LEVEL", "INFO").upper()
    logger.remove()
    if profile == "chat":
        logger.add(
            _build_chat_handler(),
            level=level,
            format="{message}",
            backtrace=False,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            format=_PROFILE_FORMATS[profile],
            backtrace=False,
            diagnose=False,
        )
        logger.configure(patcher=inject_context)
    _CONFIGURED_PROFILE = profile
