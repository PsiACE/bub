#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Render a deterministic command index from a JSON command list."""

from __future__ import annotations

import json
import sys


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.stderr.write("expected JSON list on stdin\n")
        return 1

    payload = json.loads(raw)
    if not isinstance(payload, list):
        sys.stderr.write("payload must be a JSON list\n")
        return 1

    commands: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        desc = str(item.get("description", "")).strip()
        if not name:
            continue
        commands.append((name, desc))

    for name, desc in sorted(commands, key=lambda item: item[0]):
        line = f"{name}: {desc}" if desc else name
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
