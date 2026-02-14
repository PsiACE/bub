from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_runtime_model_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUB_RUNTIME_ENABLED", "0")
