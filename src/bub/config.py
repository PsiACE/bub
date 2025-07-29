"""Configuration management for Bub."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Bub application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="BUB_",
        extra="ignore",  # Ignore extra fields from old config
    )

    # Any-LLM settings
    provider: Optional[str] = Field(default=None, description="LLM provider (e.g., openai, anthropic, ollama)")
    model_name: Optional[str] = Field(default=None, description="Model name from the provider")
    api_key: Optional[str] = Field(default=None, description="API key for the model provider")
    api_base: Optional[str] = Field(default=None, description="Custom API base URL")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens for AI responses")

    # Agent settings
    system_prompt: Optional[str] = Field(
        default="""You are Bub, a helpful AI assistant. You can:
- Read and edit files
- Run terminal commands
- Help with code development

You have access to various tools to help with coding tasks. Use them when needed to accomplish the user's requests.

Always be helpful, accurate, and follow best practices.""",
        description="System prompt for the AI agent",
    )

    # Tool settings
    workspace_path: Optional[str] = Field(default=None, description="Workspace path for file operations")


def read_bub_md(workspace_path: Optional[Path] = None) -> Optional[str]:
    """Read BUB.md file from workspace if it exists."""
    if workspace_path is None:
        workspace_path = Path.cwd()

    bub_md_path = workspace_path / "BUB.md"
    if bub_md_path.exists() and bub_md_path.is_file():
        try:
            return bub_md_path.read_text(encoding="utf-8")
        except Exception:
            # If we can't read the file, return None
            return None
    return None


def get_settings(workspace_path: Optional[Path] = None) -> Settings:
    """Get application settings, with optional BUB.md system prompt override."""
    settings = Settings()

    # Check for BUB.md file and use it as system prompt if available
    bub_md_content = read_bub_md(workspace_path)
    if bub_md_content:
        settings.system_prompt = bub_md_content.strip()

    return settings
