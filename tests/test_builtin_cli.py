from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import bub.builtin.cli as cli
from bub.framework import BubFramework


def _create_app() -> object:
    framework = BubFramework()
    framework.load_hooks()
    return framework.create_cli_app()


def test_login_openai_runs_oauth_flow_and_prints_usage_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_login_openai_codex_oauth(**kwargs: object) -> cli.OpenAICodexOAuthTokens:
        captured.update(kwargs)
        prompt_for_redirect = kwargs["prompt_for_redirect"]
        assert callable(prompt_for_redirect)
        callback = prompt_for_redirect("https://auth.openai.com/authorize")
        assert callback == "http://localhost:1455/auth/callback?code=test"
        return cli.OpenAICodexOAuthTokens(
            access_token="access",  # noqa: S106
            refresh_token="refresh",  # noqa: S106
            expires_at=123,
            account_id="acct_123",
        )

    monkeypatch.setattr(cli, "login_openai_codex_oauth", fake_login_openai_codex_oauth)
    monkeypatch.setattr(cli.typer, "prompt", lambda message: "http://localhost:1455/auth/callback?code=test")

    result = CliRunner().invoke(
        _create_app(),
        ["login", "openai", "--manual", "--no-browser", "--codex-home", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert captured["codex_home"] == tmp_path
    assert captured["open_browser"] is False
    assert captured["redirect_uri"] == cli.DEFAULT_CODEX_REDIRECT_URI
    assert captured["timeout_seconds"] == 300.0
    assert "login: ok" in result.stdout
    assert "account_id: acct_123" in result.stdout
    assert f"auth_file: {tmp_path / 'auth.json'}" in result.stdout
    assert "BUB_MODEL=openai:gpt-5-codex" in result.stdout


def test_login_openai_surfaces_oauth_errors(monkeypatch) -> None:
    def fake_login_openai_codex_oauth(**kwargs: object) -> cli.OpenAICodexOAuthTokens:
        raise cli.CodexOAuthLoginError("bad redirect")

    monkeypatch.setattr(cli, "login_openai_codex_oauth", fake_login_openai_codex_oauth)

    result = CliRunner().invoke(_create_app(), ["login", "openai", "--manual"])

    assert result.exit_code == 1
    assert "Codex login failed: bad redirect" in result.stderr


def test_login_rejects_unsupported_provider() -> None:
    result = CliRunner().invoke(_create_app(), ["login", "anthropic"])

    assert result.exit_code == 1
    assert "Unsupported auth provider: anthropic" in result.stderr
