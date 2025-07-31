"""Configuration management for Bub."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from .utils.logging import configure_logfire


class Settings(BaseSettings):
    """Application settings."""

    # API Configuration
    api_key: Optional[str] = Field(None, description="API key for the LLM provider")
    provider: Optional[str] = Field(None, description="LLM provider (e.g., 'openai', 'anthropic')")
    model_name: Optional[str] = Field(None, description="Model name (e.g., 'gpt-4', 'claude-3')")
    api_base: Optional[str] = Field(None, description="Optional API base URL")
    max_tokens: int = Field(default=4000, description="Maximum tokens for responses")

    # Agent Configuration
    timeout_seconds: int = Field(default=30, description="Timeout for AI responses in seconds")
    max_iterations: int = Field(default=10, description="Maximum number of tool execution cycles")

    # System Configuration
    system_prompt: Optional[str] = Field(None, description="System prompt for the agent")
    workspace_path: Optional[Path] = Field(None, description="Workspace directory path")

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="text", description="Log format")

    class Config:
        """Pydantic configuration."""

        env_prefix = "BUB_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


def read_bubmd(workspace_path: Path) -> str:
    """Read the bubmd file from the workspace path."""
    bubmd_path = workspace_path / "bub.md"
    if not bubmd_path.exists():
        return ""
    with open(bubmd_path, encoding="utf-8") as file:
        return file.read()


def get_settings(workspace_path: Optional[Path] = None) -> Settings:
    """Get application settings.

    Args:
        workspace_path: Optional workspace path override

    Returns:
        Settings instance
    """
    # Create settings instance - pydantic-settings will automatically load from .env file
    settings = Settings(workspace_path=workspace_path)

    configure_logfire(settings.log_level, settings.log_format)

    return settings
