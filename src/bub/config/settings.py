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
    )

    model: str = Field(default="openrouter:qwen/qwen3-coder-next")
    api_key: str | None = Field(default=None)
    api_base: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    max_tokens: int = Field(default=1024, ge=1)
    model_timeout_seconds: int = Field(default=90, ge=1)
    system_prompt: str = Field(default="")

    home: str | None = Field(default=None)
    workspace_path: str | None = Field(default=None)
    tape_name: str = Field(default="bub")
    max_steps: int = Field(default=20, ge=1)

    telegram_enabled: bool = Field(default=False)
    telegram_token: str | None = Field(default=None)
    telegram_allow_from: list[str] = Field(default_factory=list)

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
