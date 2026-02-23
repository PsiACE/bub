"""Application runtime and session management."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import signal
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from loguru import logger

from bub.app.jobstore import JSONJobStore
from bub.config.settings import Settings
from bub.core import AgentLoop, InputRouter, LoopResult, ModelRunner
from bub.integrations.republic_client import build_llm, build_tape_store, read_workspace_agents_prompt
from bub.skills.loader import SkillMetadata, discover_skills
from bub.tape import TapeService
from bub.tools import ProgressiveToolView, ToolRegistry
from bub.tools.builtin import register_builtin_tools

if TYPE_CHECKING:
    from bub.channels.manager import ChannelManager


def _session_slug(session_id: str) -> str:
    return md5(session_id.encode("utf-8")).hexdigest()[:16]  # noqa: S324


@dataclass
class SessionRuntime:
    """Runtime state for one deterministic session."""

    session_id: str
    loop: AgentLoop
    tape: TapeService
    model_runner: ModelRunner
    tool_view: ProgressiveToolView

    async def handle_input(self, text: str) -> LoopResult:
        return await self.loop.handle_input(text)

    def reset_context(self) -> None:
        """Clear volatile in-memory context while keeping the same session identity."""
        self.model_runner.reset_context()
        self.tool_view.reset()


class AppRuntime:
    """Global runtime that manages multiple session loops."""

    def __init__(
        self,
        workspace: Path,
        settings: Settings,
        *,
        allowed_tools: set[str] | None = None,
        allowed_skills: set[str] | None = None,
        enable_scheduler: bool = True,
    ) -> None:
        self.workspace = workspace.resolve()
        self.settings = settings
        self._allowed_skills = _normalize_name_set(allowed_skills)
        self._allowed_tools = _normalize_name_set(allowed_tools)
        self._store = build_tape_store(settings, self.workspace)
        self.scheduler = self._default_scheduler()
        self._llm = build_llm(settings, self._store)
        self._sessions: dict[str, SessionRuntime] = {}
        self._active_inputs: set[asyncio.Task[LoopResult]] = set()
        self._enable_scheduler = enable_scheduler

    def _default_scheduler(self) -> BaseScheduler:
        job_store = JSONJobStore(self.settings.resolve_home() / "jobs.json")
        return BackgroundScheduler(daemon=True, jobstores={"default": job_store})

    def __enter__(self) -> AppRuntime:
        if not self.scheduler.running and self._enable_scheduler:
            self.scheduler.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.scheduler.running and self._enable_scheduler:
            with suppress(Exception):
                self.scheduler.shutdown()

    def discover_skills(self) -> list[SkillMetadata]:
        discovered = discover_skills(self.workspace)
        if self._allowed_skills is None:
            return discovered
        return [skill for skill in discovered if skill.name.casefold() in self._allowed_skills]

    def get_session(self, session_id: str) -> SessionRuntime:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        tape_name = f"{self.settings.tape_name}:{_session_slug(session_id)}"
        tape = TapeService(self._llm, tape_name, store=self._store)
        tape.ensure_bootstrap_anchor()

        registry = ToolRegistry(self._allowed_tools)
        register_builtin_tools(
            registry,
            workspace=self.workspace,
            tape=tape,
            runtime=self,
            session_id=session_id,
        )
        tool_view = ProgressiveToolView(registry)
        router = InputRouter(registry, tool_view, tape, self.workspace)
        runner = ModelRunner(
            tape=tape,
            router=router,
            tool_view=tool_view,
            tools=registry.model_tools(),
            list_skills=self.discover_skills,
            model=self.settings.model,
            max_steps=self.settings.max_steps,
            max_tokens=self.settings.max_tokens,
            model_timeout_seconds=self.settings.model_timeout_seconds,
            base_system_prompt=self.settings.system_prompt,
            get_workspace_system_prompt=lambda: read_workspace_agents_prompt(self.workspace),
        )
        loop = AgentLoop(router=router, model_runner=runner, tape=tape)
        runtime = SessionRuntime(session_id=session_id, loop=loop, tape=tape, model_runner=runner, tool_view=tool_view)
        self._sessions[session_id] = runtime
        return runtime

    async def handle_input(self, session_id: str, text: str) -> LoopResult:
        session = self.get_session(session_id)
        task = asyncio.create_task(session.handle_input(text))
        self._active_inputs.add(task)
        try:
            return await task
        finally:
            self._active_inputs.discard(task)

    async def _cancel_active_inputs(self) -> int:
        """Cancel all in-flight input tasks and return canceled count."""
        count = 0
        while self._active_inputs:
            task = self._active_inputs.pop()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            count += 1
        return count

    def reset_session_context(self, session_id: str) -> None:
        """Reset volatile context for an already-created session."""
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.reset_context()

    @contextlib.asynccontextmanager
    async def graceful_shutdown(self) -> AsyncGenerator[asyncio.Event, None]:
        """Run the runtime indefinitely with graceful shutdown."""
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        handled_signals: list[signal.Signals] = []
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
                handled_signals.append(sig)
            except (NotImplementedError, RuntimeError):
                continue
        current_task = asyncio.current_task()
        future = asyncio.ensure_future(stop_event.wait())
        future.add_done_callback(lambda _, task=current_task: task and task.cancel())  # type: ignore[misc]
        try:
            yield stop_event
        finally:
            future.cancel()
            cancelled = await self._cancel_active_inputs()
            if cancelled:
                logger.info("runtime.cancel_inflight count={}", cancelled)
            for sig in handled_signals:
                with suppress(NotImplementedError, RuntimeError):
                    loop.remove_signal_handler(sig)

    def install_hooks(self, channel_manager: ChannelManager) -> None:
        """Install hooks for cross-cutting concerns like channel integration."""

        hooks_module_str = os.getenv("BUB_HOOKS_MODULE")
        if not hooks_module_str:
            return
        try:
            module = importlib.import_module(hooks_module_str)
        except ImportError as e:
            raise ImportError(f"Failed to import hooks module '{hooks_module_str}'") from e
        if not hasattr(module, "install"):
            raise AttributeError(f"Hooks module '{hooks_module_str}' does not have an 'install' function")
        hooks_context = SimpleNamespace(
            runtime=self,
            register_channel=channel_manager.register,
            default_channels=channel_manager.default_channels,
        )
        module.install(hooks_context)


def _normalize_name_set(raw: set[str] | None) -> set[str] | None:
    if raw is None:
        return None

    normalized = {name.strip().casefold() for name in raw if name.strip()}
    return normalized or None
