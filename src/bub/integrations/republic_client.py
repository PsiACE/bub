"""Republic integration helpers."""

from __future__ import annotations

from pathlib import Path

from republic import LLM

from bub.config.settings import Settings
from bub.tape.context import default_tape_context
from bub.tape.store import FileTapeStore

AGENTS_FILE = "AGENTS.md"
MAX_AGENTS_PROMPT_CHARS = 12_000


def build_tape_store(settings: Settings, workspace: Path) -> FileTapeStore:
    """Build persistent tape store for one workspace."""

    return FileTapeStore(settings.resolve_home(), workspace)


def build_llm(settings: Settings, store: FileTapeStore) -> LLM:
    """Build Republic LLM client configured for Bub runtime."""

    return LLM(
        settings.model,
        api_key=settings.resolved_api_key,
        api_base=settings.api_base,
        tape_store=store,
        context=default_tape_context(),
    )


def read_workspace_agents_prompt(workspace: Path) -> str:
    """Read workspace AGENTS.md if present."""

    prompt_file = workspace / AGENTS_FILE
    if not prompt_file.is_file():
        return ""
    try:
        content = prompt_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

    if len(content) <= MAX_AGENTS_PROMPT_CHARS:
        return content

    marker = "\n\n[AGENTS.md truncated: middle content removed]\n\n"
    head_len = (MAX_AGENTS_PROMPT_CHARS - len(marker)) // 2
    tail_len = MAX_AGENTS_PROMPT_CHARS - len(marker) - head_len
    if head_len <= 0 or tail_len <= 0:
        return content[:MAX_AGENTS_PROMPT_CHARS]
    return f"{content[:head_len]}{marker}{content[-tail_len:]}"
