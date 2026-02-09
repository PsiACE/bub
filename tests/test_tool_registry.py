from republic import Tool, ToolContext

from bub.tools.registry import ToolDescriptor, ToolRegistry


def test_registry_logs_once_for_execute(monkeypatch) -> None:
    logs: list[str] = []

    def _capture(message: str, *args: object) -> None:
        logs.append(message)

    monkeypatch.setattr("bub.tools.registry.logger.info", _capture)
    monkeypatch.setattr("bub.tools.registry.logger.exception", _capture)

    registry = ToolRegistry()

    def add(*, a: int, b: int) -> int:
        return a + b

    registry.register(
        ToolDescriptor(
            name="math.add",
            short_description="add",
            detail="add",
            tool=Tool.from_callable(add, name="math.add"),
        )
    )

    result = registry.execute("math.add", kwargs={"a": 1, "b": 2})
    assert result == 3
    assert logs.count("tool.call.start name={} run_id={} tape={} {{ {} }}") == 1
    assert logs.count("tool.call.end name={} duration={:.3f}ms") == 1


def test_registry_logs_for_direct_tool_run_with_context(monkeypatch) -> None:
    logs: list[str] = []

    def _capture(message: str, *args: object) -> None:
        logs.append(message)

    monkeypatch.setattr("bub.tools.registry.logger.info", _capture)
    monkeypatch.setattr("bub.tools.registry.logger.exception", _capture)

    registry = ToolRegistry()

    def handle(*, context: ToolContext, path: str) -> str:
        return f"{context.run_id}:{path}"

    registry.register(
        ToolDescriptor(
            name="fs.ctx",
            short_description="ctx",
            detail="ctx",
            tool=Tool(
                name="fs.ctx",
                description="ctx",
                parameters={"type": "object"},
                handler=handle,
                context=True,
            ),
        )
    )

    descriptor = registry.get("fs.ctx")
    assert descriptor is not None

    output = descriptor.tool.run(context=ToolContext(tape="t1", run_id="r1"), path="README.md")
    assert output == "r1:README.md"
    assert logs.count("tool.call.start name={} run_id={} tape={} {{ {} }}") == 1
    assert logs.count("tool.call.end name={} duration={:.3f}ms") == 1
