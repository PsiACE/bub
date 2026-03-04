import inspect
from pathlib import Path

import typer
from loguru import logger
from republic import Tool
from republic.tape import TapeStore

from bub.builtin.engine import RuntimeEngine, workspace_from_state
from bub.channels.base import Channel
from bub.channels.message import ChannelMessage
from bub.envelope import content_of, field_of
from bub.hook_runtime import HookRuntime
from bub.hookspecs import hookimpl
from bub.types import Envelope, MessageHandler, OutboundDispatcher, State

AGENTS_FILE_NAME = "AGENTS.md"


class BuiltinImpl:
    """Default hook implementations for basic runtime operations."""

    def __init__(
        self,
        hooks: HookRuntime,
        *,
        outbound_dispatcher: OutboundDispatcher | None = None,
    ) -> None:
        self.hooks = hooks
        self.engine = RuntimeEngine(hooks._plugin_manager)
        self._outbound_dispatcher = outbound_dispatcher

    @hookimpl
    def resolve_session(self, message: ChannelMessage) -> str:
        session_id = field_of(message, "session_id")
        if session_id is not None and str(session_id).strip():
            return str(session_id)
        channel = str(field_of(message, "channel", "default"))
        chat_id = str(field_of(message, "chat_id", "default"))
        return f"{channel}:{chat_id}"

    @hookimpl
    async def load_state(self, message: ChannelMessage, session_id: str) -> State:
        on_start = field_of(message, "on_start")
        if on_start is not None:
            result = on_start(message)
            if inspect.isawaitable(result):
                await result
        state = {"session_id": session_id, "_runtime_engine": self.engine}
        if context := field_of(message, "context_str"):
            state["context"] = context
        return state

    @hookimpl
    async def save_state(self, session_id: str, state: State, message: ChannelMessage, model_output: str) -> None:
        on_finish = field_of(message, "on_finish")
        if on_finish is not None:
            result = on_finish(message)
            if inspect.isawaitable(result):
                await result

    @hookimpl
    def build_prompt(self, message: ChannelMessage, session_id: str, state: State) -> str:
        _ = session_id
        workspace = field_of(message, "workspace")
        if isinstance(workspace, str) and workspace.strip():
            state["_runtime_workspace"] = workspace.strip()
        elif "_runtime_workspace" not in state:
            state["_runtime_workspace"] = str(Path.cwd())
        content = content_of(message)
        if content.startswith(","):
            message.kind = "command"
            return content
        context = field_of(message, "context_str")
        context_prefix = f"{context}\n---\n" if context else ""
        return f"{context_prefix}{content}"

    @hookimpl
    async def run_model(self, prompt: str, session_id: str, state: State) -> str:
        return await self.engine.run(session_id=session_id, prompt=prompt, state=state)

    @hookimpl
    def register_cli_commands(self, app: typer.Typer) -> None:
        from bub.builtin import cli

        app.command("run")(cli.run)
        app.command("hooks")(cli.list_hooks)
        app.command("message")(cli.message)
        app.command("chat")(cli.chat)

    @hookimpl
    def system_prompt(self, prompt: str, state: State) -> str:
        # Read the content of AGENTS.md under workspace
        prompt_path = workspace_from_state(state) / AGENTS_FILE_NAME
        if not prompt_path.is_file():
            return ""
        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @hookimpl
    def provide_tools(self) -> list[Tool]:
        from bub.builtin.tools import get_builtin_tools

        return get_builtin_tools()

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list[Channel]:
        from bub.channels.cli import CliChannel
        from bub.channels.telegram import TelegramChannel

        return [
            TelegramChannel(on_receive=message_handler),
            CliChannel(on_receive=message_handler, engine=self.engine),
        ]

    @hookimpl
    async def on_error(self, stage: str, error: Exception, message: Envelope | None) -> None:
        if message is not None:
            outbound = ChannelMessage(
                session_id=field_of(message, "session_id", "unknown"),
                channel=field_of(message, "channel", "default"),
                chat_id=field_of(message, "chat_id", "default"),
                content=f"An error occurred at stage '{stage}': {error}",
                kind="error",
            )
            await self.hooks.call_many("dispatch_outbound", message=outbound)

    @hookimpl
    async def dispatch_outbound(self, message: Envelope) -> bool:
        content = content_of(message)
        session_id = field_of(message, "session_id")
        if field_of(message, "output_channel") != "cli":
            logger.info("session.run.outbound session_id={} content={}", session_id, content)
        if self._outbound_dispatcher is None:
            return False
        return await self._outbound_dispatcher(message)

    @hookimpl
    def render_outbound(
        self,
        message: Envelope,
        session_id: str,
        state: State,
        model_output: str,
    ) -> list[ChannelMessage]:
        outbound = ChannelMessage(
            session_id=session_id,
            channel=field_of(message, "channel", "default"),
            chat_id=field_of(message, "chat_id", "default"),
            content=model_output,
            output_channel=field_of(message, "output_channel", "default"),
            kind=field_of(message, "kind", "normal"),
        )
        return [outbound]

    @hookimpl
    def provide_tape_store(self) -> TapeStore:
        from bub.builtin.store import FileTapeStore

        return FileTapeStore(directory=self.engine.settings.home / "tapes")
