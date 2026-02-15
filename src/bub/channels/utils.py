"""Utils"""

from __future__ import annotations

import contextlib
import os
import platform
import subprocess


def _proxy_from_env() -> str | None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _proxy_from_macos_system() -> str | None:
    if platform.system() != "Darwin":
        return None
    with contextlib.suppress(FileNotFoundError, subprocess.SubprocessError, UnicodeDecodeError):
        result = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, check=False, timeout=2)  # noqa: S607
        if result.returncode != 0 or not result.stdout:
            return None
        data: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if " : " not in line:
                continue
            key, value = line.split(" : ", 1)
            data[key.strip()] = value.strip()
        if data.get("HTTPSEnable") == "1":
            host = data.get("HTTPSProxy")
            port = data.get("HTTPSPort")
            if host and port:
                return f"http://{host}:{port}"
        if data.get("HTTPEnable") == "1":
            host = data.get("HTTPProxy")
            port = data.get("HTTPPort")
            if host and port:
                return f"http://{host}:{port}"
    return None


def resolve_proxy(explicit_proxy: str | None) -> tuple[str | None, str]:
    if explicit_proxy:
        return explicit_proxy, "explicit"
    env_proxy = _proxy_from_env()
    if env_proxy:
        return env_proxy, "env"
    system_proxy = _proxy_from_macos_system()
    if system_proxy:
        return system_proxy, "system"
    return None, "none"
