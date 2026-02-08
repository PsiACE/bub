"""Runtime bootstrap helpers."""

from __future__ import annotations

from pathlib import Path

from bub.app.runtime import AppRuntime
from bub.config import load_settings


def build_runtime(
    workspace: Path,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AppRuntime:
    """Build app runtime for one workspace."""

    settings = load_settings(workspace)
    updates: dict[str, object] = {}
    if model:
        updates["model"] = model
    if max_tokens is not None:
        updates["max_tokens"] = max_tokens
    if updates:
        settings = settings.model_copy(update=updates)
    return AppRuntime(workspace, settings)
