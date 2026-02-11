"""Application runtime and session management."""

from __future__ import annotations

import asyncio
from asyncio import AbstractEventLoop
from contextlib import suppress
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler

from bub.app.jobstore import JSONJobStore
from bub.config.settings import Settings
from bub.core import AgentLoop, InputRouter, LoopResult, ModelRunner
from bub.integrations.republic_client import build_llm, build_tape_store, read_workspace_agents_prompt
from bub.skills import SkillMetadata, discover_skills, load_skill_body
from bub.tape import TapeService
from bub.tools import ProgressiveToolView, ToolRegistry
from bub.tools.builtin import register_builtin_tools

if TYPE_CHECKING:
    from bub.channels.bus import MessageBus


def _session_slug(session_id: str) -> str:
    return md5(session_id.encode("utf-8")).hexdigest()[:16]  # noqa: S324


def _running_loop() -> AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


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
    ) -> None:
        self.workspace = workspace.resolve()
        self.settings = settings
        self._allowed_skills = _normalize_name_set(allowed_skills)
        self._allowed_tools = _normalize_name_set(allowed_tools)
        self._store = build_tape_store(settings, self.workspace)
        self.workspace_prompt = read_workspace_agents_prompt(self.workspace)
        self.bus: MessageBus | None = None
        self.loop: AbstractEventLoop | None = None
        self.scheduler = self._default_scheduler()
        self._llm = build_llm(settings, self._store)
        self._sessions: dict[str, SessionRuntime] = {}

    def _default_scheduler(self) -> BaseScheduler:
        job_store = JSONJobStore(self.settings.resolve_home() / "jobs.json")
        return BackgroundScheduler(daemon=True, jobstores={"default": job_store})

    def __enter__(self) -> AppRuntime:
        if not self.scheduler.running:
            self.scheduler.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.scheduler.running:
            with suppress(Exception):
                self.scheduler.shutdown()

    def discover_skills(self) -> list[SkillMetadata]:
        discovered = discover_skills(self.workspace)
        if self._allowed_skills is None:
            return discovered
        return [skill for skill in discovered if skill.name.casefold() in self._allowed_skills]

    def load_skill_body(self, skill_name: str) -> str | None:
        if self._allowed_skills is not None and skill_name.casefold() not in self._allowed_skills:
            return None
        return load_skill_body(skill_name, self.workspace)

    def _sync_running_loop(self) -> None:
        loop = _running_loop()
        if loop is not None and loop is not self.loop:
            self.loop = loop

    def get_session(self, session_id: str) -> SessionRuntime:
        self._sync_running_loop()
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
            load_skill_body=self.load_skill_body,
            model=self.settings.model,
            max_steps=self.settings.max_steps,
            max_tokens=self.settings.max_tokens,
            model_timeout_seconds=self.settings.model_timeout_seconds,
            base_system_prompt=self.settings.system_prompt,
            workspace_system_prompt=self.workspace_prompt,
        )
        loop = AgentLoop(router=router, model_runner=runner, tape=tape)
        runtime = SessionRuntime(session_id=session_id, loop=loop, tape=tape, model_runner=runner, tool_view=tool_view)
        self._sessions[session_id] = runtime
        return runtime

    async def handle_input(self, session_id: str, text: str) -> LoopResult:
        self._sync_running_loop()
        session = self.get_session(session_id)
        return await session.handle_input(text)

    def reset_session_context(self, session_id: str) -> None:
        """Reset volatile context for an already-created session."""
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.reset_context()

    def set_bus(self, bus: MessageBus) -> None:
        self.bus = bus


def _normalize_name_set(raw: set[str] | None) -> set[str] | None:
    if raw is None:
        return None

    normalized = {name.strip().casefold() for name in raw if name.strip()}
    return normalized or None
