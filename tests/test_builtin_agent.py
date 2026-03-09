from __future__ import annotations

from typing import Any

import republic.auth.openai_codex as openai_codex

import bub.builtin.agent as agent_module
from bub.builtin.settings import AgentSettings


def test_build_llm_passes_codex_resolver_to_republic(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    resolver = object()

    class FakeLLM:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(agent_module, "LLM", FakeLLM)
    monkeypatch.setattr(openai_codex, "openai_codex_oauth_resolver", lambda: resolver)
    monkeypatch.setattr(agent_module, "default_tape_context", lambda: "ctx")

    settings = AgentSettings(model="openai:gpt-5-codex", api_key=None, api_base=None)
    tape_store = object()

    agent_module._build_llm(settings, tape_store)

    assert captured["args"] == ("openai:gpt-5-codex",)
    assert captured["kwargs"]["api_key"] is None
    assert captured["kwargs"]["api_base"] is None
    assert captured["kwargs"]["api_key_resolver"] is resolver
    assert captured["kwargs"]["tape_store"] is tape_store
    assert captured["kwargs"]["context"] == "ctx"
