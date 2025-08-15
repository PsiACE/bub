"""Eventure + Huey runtime wiring for Bub.

This module wires up an EventBus from Eventure and a Huey instance whose
MemoryStorage emits events for queue/data operations. It also provides a
subscriber that executes tools upon `agent.action` events and publishes
`agent.observation`.
"""

from __future__ import annotations

import threading as _threading
import time
from pathlib import Path
from typing import Any

from eventure import EventBus, EventLog
from huey import Huey
from huey.storage import MemoryStorage

from .context import Context
from .tools import ToolExecutor, ToolRegistry


class _EventContext:
    """Thread-local parent event context for causality linking."""

    def __init__(self) -> None:
        self._local = _threading.local()

    def set_parent(self, ev) -> None:
        self._local.parent = ev

    def get_parent(self):
        return getattr(self._local, "parent", None)

    def clear(self) -> None:
        if hasattr(self._local, "parent"):
            delattr(self._local, "parent")


class EventureMemoryStorage(MemoryStorage):
    """Huey MemoryStorage that publishes queue/data events to the EventBus."""

    def __init__(
        self,
        name: str = "huey",
        event_bus: EventBus | None = None,
        ctx: _EventContext | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        if event_bus is None:
            raise ValueError
        self.event_bus = event_bus
        self._ctx = ctx or _EventContext()

    # Queue operations
    def enqueue(self, data, priority=None):
        super().enqueue(data, priority=priority)
        self.event_bus.publish(
            "huey.queue.enqueue",
            {"data": data, "priority": priority},
            parent_event=self._ctx.get_parent(),
        )

    def dequeue(self):
        data = super().dequeue()
        self.event_bus.publish("huey.queue.dequeue", {"data": data}, parent_event=self._ctx.get_parent())
        return data

    def flush_queue(self):
        super().flush_queue()
        self.event_bus.publish("huey.queue.flush", {}, parent_event=self._ctx.get_parent())

    # Result/data store operations
    def put_data(self, key, value, is_result=False):
        super().put_data(key, value, is_result=is_result)
        self.event_bus.publish(
            "huey.data.put",
            {"key": key, "value": value, "is_result": is_result},
            parent_event=self._ctx.get_parent(),
        )

    def peek_data(self, key):
        val = super().peek_data(key)
        self.event_bus.publish(
            "huey.data.peek",
            {"key": key, "value": val},
            parent_event=self._ctx.get_parent(),
        )
        return val

    def pop_data(self, key):
        val = super().pop_data(key)
        self.event_bus.publish(
            "huey.data.pop",
            {"key": key, "value": val},
            parent_event=self._ctx.get_parent(),
        )
        return val

    def flush_results(self):
        super().flush_results()
        self.event_bus.publish("huey.data.flush_results", {}, parent_event=self._ctx.get_parent())


def build_event_runtime(
    workspace_path: str | None = None,
) -> tuple[EventLog, EventBus, _EventContext, Huey, Context, ToolRegistry, ToolExecutor]:
    """Construct the evented runtime components for Bub."""
    event_log = EventLog()
    bus = EventBus(event_log)
    ctx = _EventContext()

    huey = Huey(
        name="bub-runtime",
        immediate=True,
        immediate_use_memory=False,
        storage_class=EventureMemoryStorage,
        event_bus=bus,
        ctx=ctx,
    )

    context = Context(workspace_path=Path(workspace_path) if workspace_path else None)
    registry = ToolRegistry()
    registry.register_default_tools()
    context.tool_registry = registry  # type: ignore[assignment]
    executor = ToolExecutor(context)

    return event_log, bus, ctx, huey, context, registry, executor


class ToolActionSubscriber:
    """Subscribe to `agent.action` and execute tools via ToolExecutor.

    Publishes `agent.observation` with the result or `agent.error` on failure.
    """

    def __init__(self, bus: EventBus, executor: ToolExecutor, huey: Huey, ctx: _EventContext | None = None) -> None:
        self.bus = bus
        self.executor = executor
        self.huey = huey
        self._actions: dict[str, Any] = {}
        self._ctx = ctx or _EventContext()

        @self.huey.task()
        def run_tool(action_id: str, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
            try:
                tool_result = self.executor.execute_tool(tool_name, **parameters)
                meta = self._actions.pop(action_id, None)
                parent = None
                duration_ms = None
                if isinstance(meta, tuple) and len(meta) == 2:
                    parent, start = meta
                    duration_ms = int((time.perf_counter() - start) * 1000)
                elif meta is not None:
                    parent = meta
                self.bus.publish(
                    "agent.observation",
                    {"id": action_id, "result": tool_result.model_dump(), "duration_ms": duration_ms},
                    parent_event=parent,
                )
                return tool_result.model_dump()
            except Exception as e:  # pragma: no cover - defensive
                self.bus.publish(
                    "agent.error",
                    {
                        "id": action_id,
                        "message": f"tool execution failed: {e!s}",
                    },
                )
                raise

        self._run_tool = run_tool  # keep handle for invoking
        self._unsubscribe = self.bus.subscribe("agent.action", self._on_action)

    def _on_action(self, event) -> None:
        data = event.data
        action_id = data.get("id")
        tool = data.get("tool")
        params = data.get("input", {})
        if not action_id or not isinstance(action_id, str) or not tool or not isinstance(tool, str):
            self.bus.publish(
                "agent.error",
                {
                    "id": action_id,
                    "message": "invalid action payload (missing id/tool)",
                    "payload": data,
                },
                parent_event=event,
            )
            return

        # record start time for UX metrics and keep parent for causality
        self._actions[action_id] = (event, time.perf_counter())
        # optional: action started event for UI timeline
        self.bus.publish(
            "agent.action.started",
            {"id": action_id, "tool": tool, "input": params},
            parent_event=event,
        )
        self._ctx.set_parent(event)
        try:
            # Execute task inline to ensure timely observation without a worker
            self._run_tool.call_local(action_id, tool, params)
        finally:
            self._ctx.clear()

    def close(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
