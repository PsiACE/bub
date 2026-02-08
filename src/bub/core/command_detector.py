"""Input command detection."""

from __future__ import annotations

import re
import shutil

from bub.core.commands import parse_command_words, parse_internal_command
from bub.core.types import DetectedCommand

INTERNAL_PREFIX = ","
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SAFE_PATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~/-]+$")
MAX_PATH_TOKEN_LENGTH = 240


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
        command_name, args_tokens = _shell_command_parts(words)
        return DetectedCommand(kind="shell", raw=stripped, name=command_name, args_tokens=args_tokens)

    return None


def _is_shell_command(line: str) -> bool:
    words = parse_command_words(line)
    if not words:
        return False

    env_prefixed_command = _command_word_from_env_prefix(words)
    if env_prefixed_command is not None:
        return _is_path_like(env_prefixed_command) or shutil.which(env_prefixed_command) is not None

    first_word = words[0]
    if _is_path_like(first_word):
        return True
    return shutil.which(first_word) is not None


def _is_path_like(token: str) -> bool:
    if len(token) > MAX_PATH_TOKEN_LENGTH:
        return False
    if "://" in token:
        return False
    if any(ch in token for ch in ("\n", "\r", "\t", " ", '"', "'", "`", "=")):
        return False
    if SAFE_PATH_TOKEN_RE.fullmatch(token) is None:
        return False
    return token.startswith(("./", "../", "/", "~/")) or "/" in token


def _command_word_from_env_prefix(words: list[str]) -> str | None:
    index = 0
    while index < len(words) and _is_env_assignment(words[index]):
        index += 1
    if index == 0 or index >= len(words):
        return None
    return words[index]


def _is_env_assignment(token: str) -> bool:
    if ENV_ASSIGN_RE.match(token) is None:
        return False
    _, value = token.split("=", 1)
    if not value:
        return False
    return "\n" not in value and "\r" not in value and "\t" not in value


def _shell_command_parts(words: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < len(words) and _is_env_assignment(words[index]):
        index += 1
    if index < len(words):
        return words[index], words[index + 1 :]
    return words[0], words[1:]
