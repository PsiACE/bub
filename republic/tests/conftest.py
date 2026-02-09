from __future__ import annotations

import pytest

import republic.core.execution as execution

from .fakes import FakeAnyLLMFactory


@pytest.fixture
def fake_anyllm(monkeypatch: pytest.MonkeyPatch) -> FakeAnyLLMFactory:
    factory = FakeAnyLLMFactory()
    monkeypatch.setattr(execution.AnyLLM, "create", lambda provider, **kwargs: factory.create(provider, **kwargs))
    return factory
