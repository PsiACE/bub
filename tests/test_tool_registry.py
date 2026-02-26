import pytest
from republic import ToolContext

from bub.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_registry_logs_once_for_execute(monkeypatch) -> None:
    logs: list[str] = []

    def _capture(message: str, *args: object) -> None:
        logs.append(message)

    monkeypatch.setattr("bub.tools.registry.logger.info", _capture)
    monkeypatch.setattr("bub.tools.registry.logger.exception", _capture)

    registry = ToolRegistry()

    @registry.register(name="math.add", short_description="add", detail="add")
    def add(*, a: int, b: int) -> int:
        return a + b

    result = await registry.execute("math.add", kwargs={"a": 1, "b": 2})
    assert result == 3
    assert logs.count("tool.call.start name={} {{ {} }}") == 1
    assert logs.count("tool.call.end name={} duration={:.3f}ms") == 1


@pytest.mark.asyncio
async def test_registry_logs_for_direct_tool_run_with_context(monkeypatch) -> None:
    logs: list[str] = []

    def _capture(message: str, *args: object) -> None:
        logs.append(message)

    monkeypatch.setattr("bub.tools.registry.logger.info", _capture)
    monkeypatch.setattr("bub.tools.registry.logger.exception", _capture)

    registry = ToolRegistry()

    @registry.register(name="fs.ctx", short_description="ctx", detail="ctx", context=True)
    def handle(*, context: ToolContext, path: str) -> str:
        return f"{context.run_id}:{path}"

    descriptor = registry.get("fs.ctx")
    assert descriptor is not None

    output = await descriptor.tool.run(context=ToolContext(tape="t1", run_id="r1"), path="README.md")
    assert output == "r1:README.md"
    assert logs.count("tool.call.start name={} {{ {} }}") == 1
    assert logs.count("tool.call.end name={} duration={:.3f}ms") == 1


@pytest.mark.asyncio
async def test_registry_execute_context_tool_should_work() -> None:
    registry = ToolRegistry()

    @registry.register(name="ctx.echo", short_description="echo", detail="echo", context=True)
    def echo(*, context: ToolContext, value: str) -> str:
        return f"{context.run_id}:{value}"

    ctx = ToolContext(tape="t1", run_id="r1")
    out = await registry.execute("ctx.echo", kwargs={"value": "hi"}, context=ctx)
    assert out == "r1:hi"


@pytest.mark.asyncio
async def test_registry_model_tools_use_underscore_names_and_keep_handlers() -> None:
    registry = ToolRegistry()

    @registry.register(name="fs.read", short_description="read", detail="read")
    def read(*, path: str) -> str:
        return f"read:{path}"

    rows = registry.compact_rows(for_model=True)
    assert rows == ["fs_read (command: fs.read): read"]

    model_tools = registry.model_tools()
    assert [tool.name for tool in model_tools] == ["fs_read"]
    assert await model_tools[0].run(path="README.md") == "read:README.md"


def test_registry_model_tool_name_conflict_raises_error() -> None:
    registry = ToolRegistry()

    registry.register(name="fs.read", short_description="dot", detail="dot")(lambda: "dot")
    registry.register(name="fs_read", short_description="underscore", detail="underscore")(lambda: "underscore")

    with pytest.raises(ValueError, match="Duplicate model tool name"):
        registry.model_tools()


def test_registry_restrict_to_matches_command_and_model_names() -> None:
    registry = ToolRegistry({"fs_read"})

    registry.register(name="fs.read", short_description="read", detail="read")(lambda: "read")
    registry.register(name="web.search", short_description="search", detail="search")(lambda: "search")

    assert registry.get("fs.read") is not None
    assert registry.get("web.search") is None
