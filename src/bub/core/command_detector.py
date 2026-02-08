"""Input command detection."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from bub.core.commands import parse_command_words, parse_internal_command
from bub.core.types import DetectedCommand

INTERNAL_PREFIX = ","
SHELL_SIGNAL_RE = re.compile(r"[|&;<>]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def detect_line_command(line: str) -> DetectedCommand | None:
    """Detect whether one line should be treated as command."""

    stripped = line.strip()
    if not stripped:
        return None

    if stripped.startswith(INTERNAL_PREFIX):
        name, args_tokens = parse_internal_command(stripped)
        if not name:
            return None
        return DetectedCommand(kind="internal", raw=stripped, name=name, args_tokens=args_tokens)

    if _is_shell_command(stripped):
        words = parse_command_words(stripped)
        if not words:
            return None
        return DetectedCommand(kind="shell", raw=stripped, name=words[0], args_tokens=words[1:])

    return None


def _is_shell_command(line: str) -> bool:
    if CJK_RE.search(line):
        return False
    if line.endswith((".", "!", "?", "。")):
        return False

    words = parse_command_words(line)
    if not words:
        return False

    first = words[0]
    if _is_path_like(first):
        return True

    has_signal = bool(SHELL_SIGNAL_RE.search(line))
    if has_signal:
        return True

    if ENV_ASSIGN_RE.match(first):
        return True

    return shutil.which(first) is not None


def _is_path_like(token: str) -> bool:
    if token.startswith(("./", "../", "/", "~/")):
        return True
    if os.sep in token:
        return True
    return Path(token).exists()
