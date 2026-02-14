"""Builtin runtime hook implementation."""

from __future__ import annotations

from pathlib import Path

from bub.envelope import content_of, field_of, normalize_envelope
from bub.hookspecs import hookimpl
from bub.skills.builtin.runtime.engine import RuntimeEngine
from bub.types import Envelope, State


class RuntimeSkill:
    @hookimpl
    def normalize_inbound(self, message: Envelope) -> Envelope:
        envelope = normalize_envelope(message)
        envelope["content"] = str(envelope.get("content", "")).strip()
        metadata = envelope.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.setdefault("listener", "runtime")
        envelope["metadata"] = metadata
        return envelope

    @hookimpl
    def resolve_session(self, message: Envelope) -> str:
        session_id = field_of(message, "session_id")
        if session_id is not None and str(session_id).strip():
            return str(session_id)
        channel = str(field_of(message, "channel", "default"))
        chat_id = str(field_of(message, "chat_id", "default"))
        return f"{channel}:{chat_id}"

    @hookimpl
    def build_prompt(self, message: Envelope, session_id: str, state: State) -> str:
        _ = session_id
        workspace = field_of(message, "workspace")
        if isinstance(workspace, str) and workspace.strip():
            state["_runtime_workspace"] = workspace.strip()
        elif "_runtime_workspace" not in state:
            state["_runtime_workspace"] = str(Path.cwd())
        return content_of(message)

    @hookimpl
    async def run_model(self, prompt: str, session_id: str, state: State) -> str | None:
        workspace = _workspace_from_state(state)
        engine = _engine_for_workspace(workspace)
        return await engine.run(session_id=session_id, prompt=prompt)


def _workspace_from_state(state: State) -> Path:
    raw = state.get("_runtime_workspace")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def _engine_for_workspace(workspace: Path) -> RuntimeEngine:
    cached = _ENGINE_CACHE.get(workspace)
    if cached is not None:
        return cached
    engine = RuntimeEngine(workspace)
    _ENGINE_CACHE[workspace] = engine
    return engine


_ENGINE_CACHE: dict[Path, RuntimeEngine] = {}
plugin = RuntimeSkill()
