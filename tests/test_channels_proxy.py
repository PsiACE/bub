from __future__ import annotations

from bub.channels.utils import _proxy_from_macos_system, resolve_proxy


def test_resolve_proxy_prefers_explicit_over_env(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://env.proxy:8080")
    proxy, source = resolve_proxy("http://explicit.proxy:9000")
    assert proxy == "http://explicit.proxy:9000"
    assert source == "explicit"


def test_resolve_proxy_uses_env_when_present(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://env.proxy:8080")
    proxy, source = resolve_proxy(None)
    assert proxy == "http://env.proxy:8080"
    assert source == "env"


def test_proxy_from_macos_system_parses_https(monkeypatch) -> None:
    monkeypatch.setattr("bub.channels.utils.platform.system", lambda: "Darwin")

    class _Result:
        returncode = 0
        stdout = "HTTPSEnable : 1\nHTTPSProxy : 127.0.0.1\nHTTPSPort : 7890\n"

    monkeypatch.setattr("bub.channels.utils.subprocess.run", lambda *_, **__: _Result())
    assert _proxy_from_macos_system() == "http://127.0.0.1:7890"
