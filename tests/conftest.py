from __future__ import annotations

import inspect
from typing import Any

import pytest

from bub.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _patch_tool_registry_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    async def patched_execute(
        self: ToolRegistry,
        name: str,
        *,
        kwargs: dict[str, Any],
        context: Any = None,
    ) -> Any:
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(name)

        if descriptor.tool.context:
            result = descriptor.tool.run(context=context, **kwargs)
        else:
            result = descriptor.tool.run(**kwargs)

        if inspect.isawaitable(result):
            result = await result
        return result

    monkeypatch.setattr(ToolRegistry, "execute", patched_execute)
