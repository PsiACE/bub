"""Configuration management for Bub."""

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

    # LiteLLM settings
    model: Optional[str] = Field(default=None, description="Model to use (supports various providers)")
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


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
