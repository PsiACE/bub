"""Application runtime and session management."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from hashlib import md5
from pathlib import Path

from bub.config.settings import Settings
from bub.core import AgentLoop, InputRouter, LoopResult, ModelRunner
from bub.integrations.republic_client import build_llm, build_tape_store, read_workspace_agents_prompt
from bub.skills import SkillMetadata, discover_skills, load_skill_body
from bub.tape import TapeService
from bub.tools import ProgressiveToolView, ToolRegistry
from bub.tools.builtin import register_builtin_tools


def _session_slug(session_id: str) -> str:
    return md5(session_id.encode("utf-8")).hexdigest()[:16]  # noqa: S324


@dataclass
class SessionRuntime:
    """Runtime state for one deterministic session."""

    session_id: str
    loop: AgentLoop
    tape: TapeService

    def handle_input(self, text: str) -> LoopResult:
        return self.loop.handle_input(text)


class AppRuntime:
    """Global runtime that manages multiple session loops."""

    def __init__(self, workspace: Path, settings: Settings) -> None:
        self.workspace = workspace.resolve()
        self.settings = settings
        self._store = build_tape_store(settings, self.workspace)
        self._llm = build_llm(settings, self._store)
        self._workspace_prompt = read_workspace_agents_prompt(self.workspace)
        self._skills = discover_skills(self.workspace)
        self._load_skill_body = partial(load_skill_body, workspace_path=self.workspace)
        self._sessions: dict[str, SessionRuntime] = {}

    @property
    def skills(self) -> list[SkillMetadata]:
        return list(self._skills)

    def get_session(self, session_id: str) -> SessionRuntime:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        tape_name = f"{self.settings.tape_name}:{_session_slug(session_id)}"
        tape = TapeService(self._llm, tape_name, store=self._store)
        tape.ensure_bootstrap_anchor()

        registry = ToolRegistry()
        register_builtin_tools(
            registry,
            workspace=self.workspace,
            tape=tape,
            skills=self._skills,
            load_skill_body=self._load_skill_body,
        )
        tool_view = ProgressiveToolView(registry)
        router = InputRouter(registry, tool_view, tape, self.workspace)
        runner = ModelRunner(
            tape=tape,
            router=router,
            tool_view=tool_view,
            skills=self._skills,
            load_skill_body=self._load_skill_body,
            model=self.settings.model,
            max_steps=self.settings.max_steps,
            max_tokens=self.settings.max_tokens,
            base_system_prompt=self.settings.system_prompt,
            workspace_system_prompt=self._workspace_prompt,
        )
        loop = AgentLoop(router=router, model_runner=runner, tape=tape)
        runtime = SessionRuntime(session_id=session_id, loop=loop, tape=tape)
        self._sessions[session_id] = runtime
        return runtime

    def handle_input(self, session_id: str, text: str) -> LoopResult:
        session = self.get_session(session_id)
        return session.handle_input(text)
