"""Application settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BUB_",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="null",
    )

    model: str = "openrouter:qwen/qwen3-coder-next"
    api_key: str | None = None
    api_base: str | None = None
    ollama_api_key: str | None = None
    ollama_api_base: str | None = None
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    max_tokens: int = Field(default=1024, ge=1)
    model_timeout_seconds: int | None = 90
    system_prompt: str = ""

    home: str | None = None
    workspace_path: str | None = None
    tape_name: str = "bub"
    max_steps: int = Field(default=20, ge=1)

    proactive_response: bool = False
    message_delay_seconds: int = 10
    message_debounce_seconds: int = 1
    active_time_window_seconds: int = 60

    telegram_enabled: bool = False
    telegram_token: str | None = None
    telegram_allow_from: list[str] = Field(default_factory=list)
    telegram_allow_chats: list[str] = Field(default_factory=list)
    telegram_proxy: str | None = Field(default=None)

    discord_enabled: bool = False
    discord_token: str | None = None
    discord_allow_from: list[str] = Field(default_factory=list)
    discord_allow_channels: list[str] = Field(default_factory=list)
    discord_command_prefix: str = "!"
    discord_proxy: str | None = None

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.llm_api_key:
            return self.llm_api_key
        if self.openrouter_api_key:
            return self.openrouter_api_key
        return os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")

    def resolve_home(self) -> Path:
        if self.home:
            return Path(self.home).expanduser().resolve()
        return (Path.home() / ".bub").resolve()


def load_settings(workspace_path: Path | None = None) -> Settings:
    """Load settings with optional workspace override."""

    if workspace_path is None:
        return Settings()

    return Settings(workspace_path=str(workspace_path.resolve()))
