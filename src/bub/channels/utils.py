"""Channel utility helpers."""

from __future__ import annotations


def resolve_proxy(explicit_proxy: str | None) -> tuple[str | None, str]:
    if explicit_proxy:
        return explicit_proxy, "explicit"

    # Proxy usage must be opt-in; ignore ambient env vars and OS proxy settings.
    return None, "none"
