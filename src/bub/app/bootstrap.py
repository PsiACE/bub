"""Runtime bootstrap helpers."""

from __future__ import annotations

from pathlib import Path

from bub.app.runtime import AppRuntime
from bub.config import load_settings

# Global singleton runtime instance
_runtime: AppRuntime | None = None


def get_runtime() -> AppRuntime:
    """Get or create the global app runtime."""
    if _runtime is None:
        raise RuntimeError("AppRuntime is not initialized. Call build_runtime() first.")
    return _runtime


def build_runtime(
    workspace: Path,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    allowed_tools: set[str] | None = None,
    allowed_skills: set[str] | None = None,
    enable_scheduler: bool = True,
) -> AppRuntime:
    """Build app runtime for one workspace."""

    global _runtime
    settings = load_settings(workspace)
    updates: dict[str, object] = {}
    if model:
        updates["model"] = model
    if max_tokens is not None:
        updates["max_tokens"] = max_tokens
    if updates:
        settings = settings.model_copy(update=updates)
    _runtime = AppRuntime(
        workspace,
        settings,
        allowed_tools=allowed_tools,
        allowed_skills=allowed_skills,
        enable_scheduler=enable_scheduler,
    )
    return _runtime
