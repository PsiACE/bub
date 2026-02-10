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
        self.skills: list[object] = []
        self.bus = None

    @staticmethod
    def load_skill_body(_name: str) -> str | None:
        return None


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


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.start()
    yield scheduler
    scheduler.shutdown(wait=False)


def test_web_search_default_returns_duckduckgo_url(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)
    result = registry.execute("web.search", kwargs={"query": "psiace bub"})
    assert result == "https://duckduckgo.com/?q=psiace+bub"


def test_web_fetch_default_normalizes_url_and_extracts_text(
    tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler
) -> None:
    observed_urls: list[str] = []

    class _Headers:
        def get_content_charset(self) -> str:
            return "utf-8"

    class _Response:
        headers = _Headers()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def read(self, size: int | None = None) -> bytes:
            body = b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"
            return body if size is None else body[:size]

    def _fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        _ = timeout
        observed_urls.append(request.full_url)
        return _Response()

    monkeypatch.setattr("bub.tools.builtin.urlopen", _fake_urlopen)

    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)
    result = registry.execute("web.fetch", kwargs={"url": "example.com"})

    assert observed_urls == ["https://example.com"]
    assert "Title" in result
    assert "Hello world." in result


def test_web_search_ollama_mode_calls_api(tmp_path: Path, monkeypatch: Any, scheduler: BackgroundScheduler) -> None:
    observed_request: dict[str, str] = {}

    class _Response:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def read(self) -> bytes:
            payload = {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "content": "Example snippet",
                    }
                ]
            }
            return json.dumps(payload).encode("utf-8")

    def _fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        _ = timeout
        observed_request["url"] = request.full_url
        observed_request["auth"] = request.headers.get("Authorization", "")
        observed_request["payload"] = request.data.decode("utf-8") if request.data else ""
        return _Response()

    monkeypatch.setattr("bub.tools.builtin.urlopen", _fake_urlopen)

    settings = Settings(
        _env_file=None,
        model="openrouter:test",
        ollama_api_key="ollama-test-key",
        ollama_api_base="https://search.ollama.test/api",
    )
    registry = _build_registry(tmp_path, settings, scheduler)
    result = registry.execute("web.search", kwargs={"query": "test query", "max_results": 3})

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

    class _Headers:
        def get_content_charset(self) -> str:
            return "utf-8"

    class _Response:
        headers = _Headers()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def read(self, size: int | None = None) -> bytes:
            body = b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"
            return body if size is None else body[:size]

    def _fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        _ = timeout
        observed_urls.append(request.full_url)
        return _Response()

    monkeypatch.setattr("bub.tools.builtin.urlopen", _fake_urlopen)

    settings = Settings(
        _env_file=None,
        model="openrouter:test",
        ollama_api_key="ollama-test-key",
    )
    registry = _build_registry(tmp_path, settings, scheduler)
    result = registry.execute("web.fetch", kwargs={"url": "example.com"})

    assert observed_urls == ["https://example.com"]
    assert "Title" in result
    assert "Hello world." in result


def test_schedule_add_list_remove_roundtrip(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)

    add_result = registry.execute(
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

    list_result = registry.execute("schedule.list", kwargs={})
    assert job_id in list_result
    assert "msg=hello" in list_result

    remove_result = registry.execute("schedule.remove", kwargs={"job_id": job_id})
    assert remove_result == f"removed: {job_id}"

    assert registry.execute("schedule.list", kwargs={}) == "(no scheduled jobs)"


def test_schedule_add_rejects_invalid_cron(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    settings = Settings(_env_file=None, model="openrouter:test")
    registry = _build_registry(tmp_path, settings, scheduler)

    try:
        registry.execute(
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
        registry.execute("schedule.remove", kwargs={"job_id": "missing"})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "job not found: missing" in str(exc)


def test_schedule_shared_scheduler_across_registries(tmp_path: Path, scheduler: BackgroundScheduler) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    settings = Settings(_env_file=None, model="openrouter:test")
    registry_a = _build_registry(workspace, settings, scheduler)
    registry_b = _build_registry(workspace, settings, scheduler)

    add_result = registry_a.execute(
        "schedule.add",
        kwargs={"cron": "*/5 * * * *", "message": "from-a"},
    )
    matched = re.match(r"^scheduled: (?P<job_id>[a-z0-9-]+) next=.*$", add_result)
    assert matched is not None

    assert matched.group("job_id") in registry_b.execute("schedule.list", kwargs={})
