#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Prepare a normalized runtime context payload from JSON input."""

from __future__ import annotations

import json
import sys
from typing import Any


def _session_id(payload: dict[str, Any]) -> str:
    raw = payload.get("session_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    channel = str(payload.get("channel", "default"))
    chat_id = str(payload.get("chat_id", "default"))
    return f"{channel}:{chat_id}"


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.stderr.write("expected JSON payload on stdin\n")
        return 1

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        sys.stderr.write("payload must be a JSON object\n")
        return 1

    metadata = payload.get("metadata")
    normalized_metadata: dict[str, Any] = metadata if isinstance(metadata, dict) else {}
    normalized = {
        "session_id": _session_id(payload),
        "content": str(payload.get("content", "")).strip(),
        "metadata": normalized_metadata,
    }
    normalized_metadata.setdefault("listener", "runtime")

    sys.stdout.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
