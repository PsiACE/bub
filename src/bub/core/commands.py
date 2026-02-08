"""Command parsing helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedArgs:
    """Parsed command arguments."""

    kwargs: dict[str, object]
    positional: list[str]


def parse_command_words(text: str) -> list[str]:
    """Split command text into words using shell rules."""

    try:
        return shlex.split(text)
    except ValueError:
        return []


def parse_internal_command(line: str) -> tuple[str, list[str]]:
    """Parse ',name ...' command line into name and args tokens."""

    body = line.strip()[1:].strip()
    words = parse_command_words(body)
    if not words:
        return "", []

    return words[0], words[1:]


def parse_kv_arguments(tokens: list[str]) -> ParsedArgs:
    """Parse tool arguments from tokens."""

    kwargs: dict[str, object] = {}
    positional: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]

        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                name, value = key.split("=", 1)
                kwargs[name] = value
                idx += 1
                continue

            if idx + 1 < len(tokens) and not tokens[idx + 1].startswith("--"):
                kwargs[key] = tokens[idx + 1]
                idx += 2
                continue

            kwargs[key] = True
            idx += 1
            continue

        if "=" in token:
            key, value = token.split("=", 1)
            kwargs[key] = value
            idx += 1
            continue

        positional.append(token)
        idx += 1

    return ParsedArgs(kwargs=kwargs, positional=positional)
