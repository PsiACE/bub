import asyncio
import concurrent.futures
import importlib
import threading
import time
from pathlib import Path

import pytest

from bub.app.runtime import AppRuntime, _running_loop
from bub.tools.registry import ToolRegistry

runtime_module = importlib.import_module("bub.app.runtime")


def test_running_loop_returns_none_without_active_loop() -> None:
    assert _running_loop() is None


@pytest.mark.asyncio
async def test_running_loop_returns_current_running_loop() -> None:
    assert _running_loop() is asyncio.get_running_loop()


def test_handle_input_syncs_runtime_loop_to_active_loop() -> None:
    runtime = object.__new__(AppRuntime)
    runtime.loop = None

    class _DummySession:
        async def handle_input(self, text: str) -> str:
            assert runtime.loop is asyncio.get_running_loop()
            return text

    session = _DummySession()

    def _get_session(_session_id: str) -> _DummySession:
        return session

    runtime.get_session = _get_session

    result = asyncio.run(AppRuntime.handle_input(runtime, "cli", "ping"))
    assert result == "ping"
    assert runtime.loop is not None


def test_reset_session_context_ignores_missing_session() -> None:
    runtime = object.__new__(AppRuntime)
    runtime._sessions = {}
    AppRuntime.reset_session_context(runtime, "missing")


def test_reset_session_context_resets_existing_session() -> None:
    runtime = object.__new__(AppRuntime)

    class _DummySession:
        def __init__(self) -> None:
            self.calls = 0

        def reset_context(self) -> None:
            self.calls += 1

    session = _DummySession()
    runtime._sessions = {"telegram:1": session}
    AppRuntime.reset_session_context(runtime, "telegram:1")
    assert session.calls == 1


def test_get_session_uses_isolated_registry_per_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = object.__new__(AppRuntime)
    runtime.workspace = tmp_path
    runtime.loop = None
    runtime._allowed_tools = None
    runtime._allowed_skills = None
    runtime._store = None
    runtime.workspace_prompt = ""
    runtime._llm = object()
    runtime._sessions = {}
    runtime._session_locks = {}
    runtime._session_locks_guard = threading.Lock()
    runtime.registry = ToolRegistry()
    runtime.discover_skills = lambda: []
    runtime.load_skill_body = lambda _name: None
    runtime.settings = type(
        "_Settings",
        (),
        {
            "tape_name": "bub",
            "model": "openrouter:test",
            "max_steps": 5,
            "max_tokens": 128,
            "model_timeout_seconds": 30,
            "system_prompt": "",
        },
    )()
    seen_registry_ids: dict[str, int] = {}

    class _DummyTapeService:
        def __init__(self, _llm: object, tape_name: str, *, store: object | None = None) -> None:
            _ = store
            self.tape_name = tape_name

        def ensure_bootstrap_anchor(self) -> None:
            return None

    class _DummyToolView:
        def __init__(self, registry: ToolRegistry) -> None:
            self.registry = registry

        def reset(self) -> None:
            return None

    class _DummyRouter:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

    class _DummyRunner:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def reset_context(self) -> None:
            return None

    class _DummyLoop:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

    def _fake_register_builtin_tools(
        registry: ToolRegistry,
        *,
        workspace: Path,
        tape: object,
        runtime: object,
        session_id: str,
    ) -> None:
        _ = (workspace, tape, runtime)
        seen_registry_ids[session_id] = id(registry)

    monkeypatch.setattr(runtime_module, "TapeService", _DummyTapeService)
    monkeypatch.setattr(runtime_module, "ProgressiveToolView", _DummyToolView)
    monkeypatch.setattr(runtime_module, "InputRouter", _DummyRouter)
    monkeypatch.setattr(runtime_module, "ModelRunner", _DummyRunner)
    monkeypatch.setattr(runtime_module, "AgentLoop", _DummyLoop)
    monkeypatch.setattr(runtime_module, "register_builtin_tools", _fake_register_builtin_tools)

    session_a = AppRuntime.get_session(runtime, "telegram:1")
    session_b = AppRuntime.get_session(runtime, "telegram:2")

    assert session_a.registry is not session_b.registry
    assert seen_registry_ids["telegram:1"] != seen_registry_ids["telegram:2"]


def test_get_session_is_initialized_once_per_session_under_concurrency(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = object.__new__(AppRuntime)
    runtime.workspace = tmp_path
    runtime.loop = None
    runtime._allowed_tools = None
    runtime._allowed_skills = None
    runtime._store = None
    runtime.workspace_prompt = ""
    runtime._llm = object()
    runtime._sessions = {}
    runtime._session_locks = {}
    runtime._session_locks_guard = threading.Lock()
    runtime.registry = ToolRegistry()
    runtime.discover_skills = lambda: []
    runtime.load_skill_body = lambda _name: None
    runtime.settings = type(
        "_Settings",
        (),
        {
            "tape_name": "bub",
            "model": "openrouter:test",
            "max_steps": 5,
            "max_tokens": 128,
            "model_timeout_seconds": 30,
            "system_prompt": "",
        },
    )()
    calls = {"register": 0}

    class _DummyTapeService:
        def __init__(self, _llm: object, _tape_name: str, *, store: object | None = None) -> None:
            _ = store

        def ensure_bootstrap_anchor(self) -> None:
            return None

    class _DummyToolView:
        def __init__(self, registry: ToolRegistry) -> None:
            self.registry = registry

        def reset(self) -> None:
            return None

    class _DummyRouter:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

    class _DummyRunner:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def reset_context(self) -> None:
            return None

    class _DummyLoop:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

    def _fake_register_builtin_tools(
        _registry: ToolRegistry,
        *,
        workspace: Path,
        tape: object,
        runtime: object,
        session_id: str,
    ) -> None:
        _ = (workspace, tape, runtime, session_id)
        calls["register"] += 1
        time.sleep(0.02)

    monkeypatch.setattr(runtime_module, "TapeService", _DummyTapeService)
    monkeypatch.setattr(runtime_module, "ProgressiveToolView", _DummyToolView)
    monkeypatch.setattr(runtime_module, "InputRouter", _DummyRouter)
    monkeypatch.setattr(runtime_module, "ModelRunner", _DummyRunner)
    monkeypatch.setattr(runtime_module, "AgentLoop", _DummyLoop)
    monkeypatch.setattr(runtime_module, "register_builtin_tools", _fake_register_builtin_tools)

    def _get() -> object:
        return AppRuntime.get_session(runtime, "telegram:1")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        sessions = list(executor.map(lambda _idx: _get(), range(16)))

    assert calls["register"] == 1
    first = sessions[0]
    assert all(session is first for session in sessions)
