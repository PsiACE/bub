from pathlib import Path

import typer
from pluggy import PluginManager

from bub.builtin.engine import RuntimeEngine
from bub.envelope import content_of, field_of, normalize_envelope
from bub.hookspecs import hookimpl
from bub.types import Envelope, State

AGENTS_FILE_NAME = "AGENTS.md"


class BuiltinImpl:
    """Default hook implementations for basic runtime operations."""

    def __init__(self, plugin_manager: PluginManager) -> None:
        self.plugin_manager = plugin_manager
        self.engine = RuntimeEngine(plugin_manager)

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
    def load_state(self, session_id: str) -> State:
        return {"session_id": session_id, "_runtime_engine": self.engine}

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
    async def run_model(self, prompt: str, session_id: str, state: State) -> str:
        return await self.engine.run(session_id=session_id, prompt=prompt, state=state)

    @hookimpl
    def register_cli_commands(self, app: typer.Typer) -> None:
        from bub.builtin import cli

        app.command("run")(cli.run)
        app.command("hooks")(cli.list_hooks)
        app.command("install")(cli.install_plugin)

    @hookimpl
    def system_prompt(self, state: State) -> str:
        # Read the content of AGENTS.md under workspace
        prompt_path = _workspace_from_state(state) / AGENTS_FILE_NAME
        if not prompt_path.is_file():
            return ""
        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""


def _workspace_from_state(state: State) -> Path:
    raw = state.get("_runtime_workspace")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()
