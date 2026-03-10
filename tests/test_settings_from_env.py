from __future__ import annotations

from unittest.mock import patch

from bub.builtin.settings import AgentSettings


def _from_env_with(env: dict[str, str]) -> AgentSettings:
    """Call AgentSettings.from_env() with a controlled env, bypassing .env file and real os.environ."""
    with (
        patch("dotenv.dotenv_values", return_value={}),
        patch.dict("os.environ", env, clear=True),
    ):
        return AgentSettings.from_env()


def test_from_env_single_api_key_and_base() -> None:
    """When BUB_API_KEY and BUB_API_BASE are both set, return plain AgentSettings."""
    settings = _from_env_with({"BUB_API_KEY": "sk-test", "BUB_API_BASE": "https://api.example.com"})

    assert isinstance(settings.api_key, str)
    assert isinstance(settings.api_base, str)


def test_from_env_per_provider_keys() -> None:
    """When per-provider BUB_<PROVIDER>_API_KEY vars are set, build a dict."""
    settings = _from_env_with({
        "BUB_OPENAI_API_KEY": "sk-openai",
        "BUB_OPENAI_API_BASE": "https://api.openai.com",
        "BUB_ANTHROPIC_API_KEY": "sk-anthropic",
    })

    assert isinstance(settings.api_key, dict)
    assert settings.api_key["openai"] == "sk-openai"
    assert settings.api_key["anthropic"] == "sk-anthropic"
    assert isinstance(settings.api_base, dict)
    assert settings.api_base["openai"] == "https://api.openai.com"


def test_from_env_no_keys_returns_none() -> None:
    """When no API key env vars are present, api_key and api_base are None."""
    settings = _from_env_with({})

    assert settings.api_key is None
    assert settings.api_base is None


def test_from_env_provider_names_are_lowercased() -> None:
    """Provider names extracted from env vars should be lowercased."""
    settings = _from_env_with({"BUB_OPENROUTER_API_KEY": "sk-or"})

    assert isinstance(settings.api_key, dict)
    assert "openrouter" in settings.api_key


def test_from_env_mixed_single_key_with_per_provider_base() -> None:
    """When BUB_API_KEY is set but BUB_API_BASE is not, key stays string, base becomes dict."""
    settings = _from_env_with({
        "BUB_API_KEY": "sk-global",
        "BUB_OPENAI_API_BASE": "https://api.openai.com",
    })

    # api_key is a plain string (from BUB_API_KEY), base is a dict
    assert settings.api_key == "sk-global"
    assert isinstance(settings.api_base, dict)
    assert settings.api_base["openai"] == "https://api.openai.com"


def test_from_env_dotenv_file_values_used() -> None:
    """Values from .env file are used when present."""
    dotenv_data = {"BUB_OPENAI_API_KEY": "sk-from-dotenv"}
    with (
        patch("dotenv.dotenv_values", return_value=dotenv_data),
        patch.dict("os.environ", {}, clear=True),
    ):
        settings = AgentSettings.from_env()

    assert isinstance(settings.api_key, dict)
    assert settings.api_key["openai"] == "sk-from-dotenv"


def test_from_env_os_environ_overrides_dotenv() -> None:
    """os.environ should override values from .env file."""
    dotenv_data = {"BUB_OPENAI_API_KEY": "sk-from-dotenv"}
    with (
        patch("dotenv.dotenv_values", return_value=dotenv_data),
        patch.dict("os.environ", {"BUB_OPENAI_API_KEY": "sk-from-env"}, clear=True),
    ):
        settings = AgentSettings.from_env()

    assert isinstance(settings.api_key, dict)
    assert settings.api_key["openai"] == "sk-from-env"
