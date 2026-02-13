"""Hook-first Bub framework runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pluggy
from loguru import logger

from bub.bus import BusProtocol, MessageBus
from bub.envelope import content_of, field_of, unpack_batch
from bub.hook_runtime import HookRuntime
from bub.hookspecs import BUB_HOOK_NAMESPACE, BubHookSpecs
from bub.skills.loader import SkillMetadata, discover_hook_skills, load_skill_plugin
from bub.types import Envelope, TurnResult

SOURCE_PRIORITY = {"builtin": 0, "global": 1, "project": 2}


@dataclass(frozen=True)
class LoadedSkill:
    """Runtime registration result for one skill."""

    skill: SkillMetadata
    plugin_name: str


class BubFramework:
    """Minimal framework core. Everything grows from hook skills."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self._plugin_manager = pluggy.PluginManager(BUB_HOOK_NAMESPACE)
        self._plugin_manager.add_hookspecs(BubHookSpecs)
        self._hook_runtime = HookRuntime(self._plugin_manager)
        self._loaded_skills: list[LoadedSkill] = []
        self._failed_skills: dict[str, str] = {}

    @property
    def loaded_skills(self) -> list[LoadedSkill]:
        return list(self._loaded_skills)

    @property
    def failed_skills(self) -> dict[str, str]:
        return dict(self._failed_skills)

    def load_skills(self) -> None:
        """Discover and register all hook skills."""

        self._loaded_skills = []
        self._failed_skills = {}

        skills = sorted(discover_hook_skills(self.workspace), key=self._registration_order_key)
        for skill in skills:
            plugin_name = f"{skill.source}:{skill.name}"
            try:
                plugin = load_skill_plugin(skill)
                self._plugin_manager.register(plugin, name=plugin_name)
                self._loaded_skills.append(LoadedSkill(skill=skill, plugin_name=plugin_name))
            except Exception as exc:  # pragma: no cover - exercised via behavior tests
                self._failed_skills[skill.name] = str(exc)
                logger.opt(exception=True).warning("skill.load_failed skill={} source={}", skill.name, skill.source)

    def create_bus(self) -> BusProtocol:
        """Create bus instance from hooks; fallback to default in-memory bus."""

        provided = self._hook_runtime.call_first_sync("provide_bus")
        if self._is_bus_like(provided):
            return cast(BusProtocol, provided)
        return MessageBus()

    def register_cli_commands(self, app: Any) -> None:
        """Ask skills to register CLI commands."""

        self._hook_runtime.call_many_sync("register_cli_commands", app=app)

    async def process_inbound(self, inbound: Envelope) -> TurnResult:
        """Run one inbound message through hooks and return turn result."""

        try:
            normalized = await self._hook_runtime.call_first("normalize_inbound", message=inbound)
            message = normalized if normalized is not None else inbound
            session_id = await self._hook_runtime.call_first("resolve_session", message=message) or self._default_session_id(
                message
            )
            state = await self._hook_runtime.call_first("load_state", session_id=session_id) or {}
            if not isinstance(state, dict):
                state = {}
            prompt = await self._hook_runtime.call_first("build_prompt", message=message, session_id=session_id, state=state)
            if not prompt:
                prompt = content_of(message)
            model_output = await self._hook_runtime.call_first("run_model", prompt=prompt, session_id=session_id, state=state)
            if model_output is None:
                await self._hook_runtime.notify_error(
                    stage="run_model:fallback",
                    error=RuntimeError("no model skill returned output"),
                    message=message,
                )
                model_output = prompt
            else:
                model_output = str(model_output)

            await self._hook_runtime.call_many(
                "save_state",
                session_id=session_id,
                state=state,
                message=message,
                model_output=model_output,
            )
            outbounds = await self._collect_outbounds(message, session_id, state, model_output)
            for outbound in outbounds:
                await self._hook_runtime.call_many("dispatch_outbound", message=outbound)
            return TurnResult(session_id=session_id, prompt=prompt, model_output=model_output, outbounds=outbounds)
        except Exception as exc:
            await self._hook_runtime.notify_error(stage="turn", error=exc, message=inbound)
            raise

    async def handle_bus_once(self, bus: BusProtocol | None = None, *, timeout_seconds: float | None = None) -> TurnResult | None:
        """Consume one inbound message from bus and publish generated outbounds."""

        active_bus = bus or self.create_bus()
        inbound = await active_bus.next_inbound(timeout_seconds=timeout_seconds)
        if inbound is None:
            return None
        result = await self.process_inbound(inbound)
        for outbound in result.outbounds:
            await active_bus.publish_outbound(outbound)
        return result

    def hook_report(self) -> dict[str, list[str]]:
        """Return hook implementation summary for diagnostics."""

        return self._hook_runtime.hook_report()

    @staticmethod
    def _default_session_id(message: Envelope) -> str:
        session_id = field_of(message, "session_id")
        if session_id is not None:
            return str(session_id)
        channel = str(field_of(message, "channel", "default"))
        chat_id = str(field_of(message, "chat_id", "default"))
        return f"{channel}:{chat_id}"

    async def _collect_outbounds(
        self,
        message: Envelope,
        session_id: str,
        state: dict[str, Any],
        model_output: str,
    ) -> list[Envelope]:
        batches = await self._hook_runtime.call_many(
            "render_outbound",
            message=message,
            session_id=session_id,
            state=state,
            model_output=model_output,
        )
        outbounds: list[Envelope] = []
        for batch in batches:
            outbounds.extend(unpack_batch(batch))
        if outbounds:
            return outbounds

        fallback: dict[str, Any] = {
            "content": model_output,
            "session_id": session_id,
        }
        channel = field_of(message, "channel")
        chat_id = field_of(message, "chat_id")
        if channel is not None:
            fallback["channel"] = channel
        if chat_id is not None:
            fallback["chat_id"] = chat_id
        return [fallback]

    @staticmethod
    def _registration_order_key(skill: SkillMetadata) -> tuple[int, str]:
        return (SOURCE_PRIORITY.get(skill.source, 3), skill.name.casefold())

    @staticmethod
    def _is_bus_like(candidate: Any) -> bool:
        if candidate is None:
            return False
        required = ("publish_inbound", "publish_outbound", "next_inbound", "next_outbound")
        return all(callable(getattr(candidate, name, None)) for name in required)
