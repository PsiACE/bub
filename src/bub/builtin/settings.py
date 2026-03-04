import pathlib

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "openrouter:qwen/qwen3-coder-next"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_HOME = pathlib.Path.home() / ".bub"


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUB_", env_parse_none_str="null", extra="ignore", env_file=".env")

    home: pathlib.Path = Field(default=DEFAULT_HOME)

    model: str = DEFAULT_MODEL
    api_key: str | None = None
    api_base: str | None = None
    max_steps: int = 50
    max_tokens: int = DEFAULT_MAX_TOKENS
    model_timeout_seconds: int | None = None
