from __future__ import annotations

from bub.builtin.settings import AgentSettings


def test_agent_settings_reads_api_format_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BUB_API_FORMAT", "responses")

    settings = AgentSettings()

    assert settings.api_format == "responses"
