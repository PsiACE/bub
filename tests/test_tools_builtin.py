import asyncio
import inspect
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from bub.config.settings import Settings
from bub.tools.builtin import register_builtin_tools
from bub.tools.registry import ToolRegistry


@dataclass
class _TapeInfo:
    name: str = "bub"
    entries: int = 0
    anchors: int = 0
    last_anchor: str | None = None


class _DummyTape:
    def handoff(self, _name: str, *, state: dict[str, object] | None = None) -> list[object]:
        _ = state
        return []

    def anchors(self, *, limit: int = 20) -> list[object]:
        _ = limit
        return []

    def info(self) -> _TapeInfo:
        return _TapeInfo()

    def search(self, _query: str, *, limit: int = 20) -> list[object]:
        _ = limit
        return []

    def reset(self, *, archive: bool = False) -> str:
        _ = archive
        return "reset"


class _DummyRuntime:
    def __init__(self, settings: Settings, scheduler: BackgroundScheduler) -> None:
        self.settings = settings
        self.scheduler = scheduler
        self._discovered_skills: list[object] = []
        self.bus = None
        self.reset_calls: list[str] = []
        self.workspace = Path.cwd()

    def discover_skills(self) -> list[object]:
        return list(self._discovered_skills)

    @staticmethod
    def load_skill_body(_name: str) -> str | None:
        return None

    def reset_session_context(self, session_id: str) -> None:
        self.reset_calls.append(session_id)


def _build_registry(workspace: Path, settings: Settings, scheduler: BackgroundScheduler) -> ToolRegistry:
    registry = ToolRegistry()
    runtime = _DummyRuntime(settings, scheduler)
    register_builtin_tools(
        registry,
        workspace=workspace,
        tape=_DummyTape(),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        session_id="cli:test",
    )
    return registry


def _execute_tool(registry: ToolRegistry, name: str, *, kwargs: dict[str, Any]) -> Any:
    descriptor = registry.get(name)
    if descriptor is not None and descriptor.tool.context:
        result = descriptor.tool.run(context=None, **kwargs)
    else:
        result = registry.execute(name, kwargs=kwargs)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.start()
    yield scheduler
    scheduler.shutdown(wait=False)


def test_web_search_default_returns_duckduckgo_url(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)
    result = _execute_tool(registry, "web.search", kwargs={"query": "psiace bub"})
    assert result == "https://duckduckgo.com/?q=psiace+bub"


def test_web_fetch_default_normalizes_url_and_extracts_text(
    tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler
) -> None:
    observed_urls: list[str] = []

    class _Response:
        class _Content:
            @staticmethod
            async def read(_size: int | None = None) -> bytes:
                return b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"

        content = _Content()

    class _RequestCtx:
        def __init__(self, response: _Response) -> None:
            self._response = response

        async def __aenter__(self) -> _Response:
            return self._response

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def get(self, url: str, *, headers: dict[str, str]) -> _RequestCtx:
            _ = headers
            observed_urls.append(url)
            return _RequestCtx(_Response())

    monkeypatch.setattr("aiohttp.ClientSession", lambda *args, **kwargs: _Session())

    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)
    result = _execute_tool(registry, "web.fetch", kwargs={"url": "example.com"})

    assert observed_urls == ["https://example.com"]
    assert "Title" in result
    assert "Hello world." in result


def test_web_search_ollama_mode_calls_api(tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler) -> None:
    observed_request: dict[str, str] = {}

    class _Response:
        @staticmethod
        async def text() -> str:
            payload = {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "content": "Example snippet",
                    }
                ]
            }
            return json.dumps(payload)

    class _RequestCtx:
        def __init__(self, response: _Response) -> None:
            self._response = response

        async def __aenter__(self) -> _Response:
            return self._response

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]) -> _RequestCtx:
            import json as json_lib

            observed_request["url"] = url
            observed_request["auth"] = headers.get("Authorization", "")
            observed_request["payload"] = json_lib.dumps(json)
            return _RequestCtx(_Response())

    monkeypatch.setattr("aiohttp.ClientSession", lambda *args, **kwargs: _Session())

    settings = Settings(
        _env_file=None,
        model="openrouter:test",
        ollama_api_key="ollama-test-key",
        ollama_api_base="https://search.ollama.test/api",
    )
    registry = _build_registry(tmp_path, settings, scheduler)
    result = _execute_tool(registry, "web.search", kwargs={"query": "test query", "max_results": 3})

    assert observed_request["url"] == "https://search.ollama.test/api/web_search"
    assert observed_request["auth"] == "Bearer ollama-test-key"
    assert json.loads(observed_request["payload"]) == {"query": "test query", "max_results": 3}
    assert "Example" in result
    assert "https://example.com" in result
    assert "Example snippet" in result


def test_web_fetch_ollama_mode_normalizes_url_and_extracts_text(
    tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler
) -> None:
    observed_urls: list[str] = []

    class _Response:
        class _Content:
            @staticmethod
            async def read(_size: int | None = None) -> bytes:
                return b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"

        content = _Content()

    class _RequestCtx:
        def __init__(self, response: _Response) -> None:
            self._response = response

        async def __aenter__(self) -> _Response:
            return self._response

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def get(self, url: str, *, headers: dict[str, str]) -> _RequestCtx:
            _ = headers
            observed_urls.append(url)
            return _RequestCtx(_Response())

    monkeypatch.setattr("aiohttp.ClientSession", lambda *args, **kwargs: _Session())

    settings = Settings(
        _env_file=None,
        model="openrouter:test",
        ollama_api_key="ollama-test-key",
    )
    registry = _build_registry(tmp_path, settings, scheduler)
    result = _execute_tool(registry, "web.fetch", kwargs={"url": "example.com"})

    assert observed_urls == ["https://example.com"]
    assert "Title" in result
    assert "Hello world." in result


def test_schedule_add_list_remove_roundtrip(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)

    add_result = _execute_tool(
        registry,
        "schedule.add",
        kwargs={
            "cron": "*/5 * * * *",
            "message": "hello",
        },
    )
    assert add_result.startswith("scheduled: ")
    matched = re.match(r"^scheduled: (?P<job_id>[a-z0-9-]+) next=.*$", add_result)
    assert matched is not None
    job_id = matched.group("job_id")

    list_result = _execute_tool(registry, "schedule.list", kwargs={})
    assert job_id in list_result
    assert "msg=hello" in list_result

    remove_result = _execute_tool(registry, "schedule.remove", kwargs={"job_id": job_id})
    assert remove_result == f"removed: {job_id}"

    assert _execute_tool(registry, "schedule.list", kwargs={}) == "(no scheduled jobs)"


def test_schedule_add_rejects_invalid_cron(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)

    try:
        _execute_tool(
            registry,
            "schedule.add",
            kwargs={"cron": "* * *", "message": "bad"},
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "invalid cron expression" in str(exc)


def test_schedule_remove_missing_job_returns_error(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)

    try:
        _execute_tool(registry, "schedule.remove", kwargs={"job_id": "missing"})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "job not found: missing" in str(exc)


def test_schedule_shared_scheduler_across_registries(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    settings = Settings(_env_file=None, model="openrouter:test")
    registry_a = _build_registry(workspace, settings, scheduler)
    registry_b = _build_registry(workspace, settings, scheduler)

    add_result = _execute_tool(
        registry_a,
        "schedule.add",
        kwargs={"cron": "*/5 * * * *", "message": "from-a"},
    )
    matched = re.match(r"^scheduled: (?P<job_id>[a-z0-9-]+) next=.*$", add_result)
    assert matched is not None

    assert matched.group("job_id") in _execute_tool(registry_b, "schedule.list", kwargs={})


def test_skills_list_uses_latest_runtime_skills(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    @dataclass(frozen=True)
    class _Skill:
        name: str
        description: str

    class _Runtime:
        def __init__(self, settings: Settings, scheduler: BackgroundScheduler) -> None:
            self.settings = settings
            self.scheduler = scheduler
            self.bus = None
            self._discovered_skills: list[_Skill] = [_Skill(name="alpha", description="first")]

        def discover_skills(self) -> list[_Skill]:
            return list(self._discovered_skills)

        @staticmethod
        def load_skill_body(_name: str) -> str | None:
            return None

    settings = Settings(_env_file=None, model="openrouter:test")
    runtime = _Runtime(settings, scheduler)
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        workspace=tmp_path,
        tape=_DummyTape(),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        session_id="cli:test",
    )

    assert _execute_tool(registry, "skills.list", kwargs={}) == "alpha: first"

    runtime._discovered_skills.append(_Skill(name="beta", description="second"))
    second = _execute_tool(registry, "skills.list", kwargs={})
    assert "alpha: first" in second
    assert "beta: second" in second


def test_bash_tool_inherits_runtime_session_id(
    tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler
) -> None:
    observed: dict[str, object] = {}

    class _Completed:
        returncode = 0

        @staticmethod
        async def communicate() -> tuple[bytes, bytes]:
            return b"ok", b""

    async def _fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> _Completed:
        observed["args"] = args
        observed["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr("bub.tools.builtin.asyncio.create_subprocess_exec", _fake_create_subprocess_exec)

    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)
    result = _execute_tool(registry, "bash", kwargs={"cmd": "echo hi"})

    assert result == "ok"
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["env"]["BUB_SESSION_ID"] == "cli:test"


def test_tape_reset_also_clears_session_runtime_context(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    runtime = _DummyRuntime(settings, scheduler)
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        workspace=tmp_path,
        tape=_DummyTape(),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        session_id="telegram:123",
    )

    result = _execute_tool(registry, "tape.reset", kwargs={"archive": True})
    assert result == "reset"
    assert runtime.reset_calls == ["telegram:123"]
