"""Configuration management for Bub."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .skills import build_skills_prompt_section


class Settings(BaseSettings):
    """Bub application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="BUB_",
        extra="ignore",
    )

    # Republic model settings
    model: str | None = Field(
        default=None,
        description="Model identifier in provider:model format (e.g., openai:gpt-4o-mini)",
    )
    api_key: str | None = Field(default=None, description="API key for the model provider")
    api_base: str | None = Field(default=None, description="Custom API base URL")
    max_tokens: int | None = Field(default=None, description="Maximum tokens for AI responses")

    # Agent settings
    system_prompt: str | None = Field(
        default=(
            "You are Bub, a concise coding assistant.\n"
            "Use tools when they help you answer or modify the project.\n"
            "Available tools: fs_read, fs_write, fs_edit, fs_glob, fs_grep, bash, tape_search, tape_anchors, "
            "tape_info, tape_reset, handoff, status, help, tools.\n"
            "Use exact tool names as listed above for tool calling.\n"
            "Tool observations are returned as JSON with keys: tool, signature, category, status, repeat, "
            "machine_readable, human_preview.\n"
            "If a tool observation status is stagnant, stop repeating that call and provide a final answer.\n"
            "When the user asks for verification, prefer including successful verification tool results in your "
            "final response.\n"
            "Do not call handoff or status unless the user explicitly asks for them.\n"
            "When using bash, run commands relative to the current workspace; do not assume fixed paths.\n"
            "End your run by outputting $done on its own line.\n"
            "If you issue commands, continue until you can provide a final response.\n"
            "Return clear, direct responses."
        ),
        description="System prompt for the AI agent",
    )

    # Tool settings
    workspace_path: str | None = Field(default=None, description="Workspace path for file operations")


def find_agents_md(workspace_path: Path | None = None) -> Path | None:
    """Find the nearest AGENTS.md file starting from the workspace path."""
    start = Path.cwd() if workspace_path is None else workspace_path

    start = start if start.is_dir() else start.parent
    start = start.resolve()

    for parent in [start, *start.parents]:
        candidate = parent / "AGENTS.md"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def read_agents_md(workspace_path: Path | None = None) -> str | None:
    """Read AGENTS.md file from workspace if it exists."""
    agents_md_path = find_agents_md(workspace_path)
    if not agents_md_path:
        return None
    try:
        return agents_md_path.read_text(encoding="utf-8")
    except OSError:
        return None


def get_settings(workspace_path: Path | None = None) -> Settings:
    """Get application settings, with optional AGENTS.md system prompt override."""
    settings = Settings()

    agents_md_content = read_agents_md(workspace_path)
    if agents_md_content:
        settings.system_prompt = agents_md_content.strip()

    skills_section = build_skills_prompt_section(workspace_path)
    if skills_section:
        settings.system_prompt = _append_prompt_section(settings.system_prompt, skills_section)

    return settings


def _append_prompt_section(base: str | None, section: str) -> str:
    base_text = (base or "").strip()
    section_text = section.strip()
    if not base_text:
        return section_text
    return f"{base_text}\n\n{section_text}"
