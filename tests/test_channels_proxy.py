from __future__ import annotations

from bub.channels.utils import resolve_proxy


def test_resolve_proxy_prefers_explicit_over_ambient(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://env.proxy:8080")
    proxy, source = resolve_proxy("http://explicit.proxy:9000")
    assert proxy == "http://explicit.proxy:9000"
    assert source == "explicit"


def test_resolve_proxy_is_opt_in(monkeypatch) -> None:
    proxy, source = resolve_proxy(None)
    assert proxy is None
    assert source == "none"
