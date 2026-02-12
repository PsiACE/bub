"""Republic integration helpers."""

from __future__ import annotations

from pathlib import Path

from republic import LLM

from bub.config.settings import Settings
from bub.tape.context import default_tape_context
from bub.tape.store import FileTapeStore

AGENTS_FILE = "AGENTS.md"


def build_tape_store(settings: Settings, workspace: Path) -> FileTapeStore:
    """Build persistent tape store for one workspace."""

    return FileTapeStore(settings.resolve_home(), workspace)


def build_llm(settings: Settings, store: FileTapeStore) -> LLM:
    """Build Republic LLM client configured for Bub runtime."""

    client_args = None
    if "azure" in settings.model:
        client_args = {"api_version": "2025-01-01-preview"}

    return LLM(
        settings.model,
        api_key=settings.resolved_api_key,
        api_base=settings.api_base,
        tape_store=store,
        context=default_tape_context(),
        client_args=client_args,
    )


def read_workspace_agents_prompt(workspace: Path) -> str:
    """Read workspace AGENTS.md if present."""

    prompt_file = workspace / AGENTS_FILE
    if not prompt_file.is_file():
        return ""
    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
