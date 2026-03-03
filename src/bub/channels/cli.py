"""CLI channel adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from hashlib import md5
from pathlib import Path

from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich import get_console

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel
from bub.cli.render import CliRenderer
from bub.core.agent_loop import LoopResult


class CliChannel(BaseChannel[str]):
    """Interactive terminal channel."""

    name = "cli"

    def __init__(self, runtime: AppRuntime, *, session_id: str = "cli") -> None:
        super().__init__(runtime)
        self._session_id = session_id
        self._session = runtime.get_session(session_id)
        self._renderer = CliRenderer(get_console())
        self._mode = "agent"
        self._last_tape_info: object | None = None
        self._prompt = self._build_prompt()
        self._stop_requested = False

    @property
    def debounce_enabled(self) -> bool:
        return False

    async def start(self, on_receive: Callable[[str], Awaitable[None]]) -> None:
        self._renderer.welcome(model=self.runtime.settings.model, workspace=str(self.runtime.workspace))
        await self._refresh_tape_info()

        while not self._stop_requested:
            try:
                with patch_stdout(raw=True):
                    raw = (await self._prompt.prompt_async(self._prompt_message())).strip()
            except KeyboardInterrupt:
                self._renderer.info("Interrupted. Use ',quit' to exit.")
                continue
            except EOFError:
                break

            if not raw:
                continue

            request = self._normalize_input(raw)
            with self._renderer.console.status("[cyan]Processing...[/cyan]", spinner="dots"):
                await on_receive(request)

        self._renderer.info("Bye.")

    def is_mentioned(self, message: str) -> bool:
        _ = message
        return True

    async def get_session_prompt(self, message: str) -> tuple[str, str]:
        return self._session_id, message

    def format_prompt(self, prompt: str) -> str:
        return prompt

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        _ = session_id
        await self._refresh_tape_info()
        if output.immediate_output:
            self._renderer.command_output(output.immediate_output)
        if output.error:
            self._renderer.error(output.error)
        if output.assistant_output:
            self._renderer.assistant_output(output.assistant_output)
        if output.exit_requested:
            self._stop_requested = True

    async def _refresh_tape_info(self) -> None:
        try:
            self._last_tape_info = await self._session.tape.info()
        except Exception as exc:
            self._last_tape_info = None
            logger.debug("cli.tape_info.unavailable session_id={} error={}", self._session_id, exc)

    def _build_prompt(self) -> PromptSession[str]:
        kb = KeyBindings()

        @kb.add("c-x", eager=True)
        def _toggle_mode(event) -> None:
            self._mode = "shell" if self._mode == "agent" else "agent"
            event.app.invalidate()

        def _tool_sort_key(tool_name: str) -> tuple[str, str]:
            section, _, name = tool_name.rpartition(".")
            return (section, name)

        history_file = self._history_file(self.runtime.settings.resolve_home(), self.runtime.workspace)
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_file))
        tool_names = sorted((f",{tool}" for tool in self._session.tool_view.all_tools()), key=_tool_sort_key)
        completer = WordCompleter(tool_names, ignore_case=True)
        return PromptSession(
            completer=completer,
            complete_while_typing=True,
            key_bindings=kb,
            history=history,
            bottom_toolbar=self._render_bottom_toolbar,
        )

    def _prompt_message(self) -> FormattedText:
        cwd = Path.cwd().name
        symbol = ">" if self._mode == "agent" else ","
        return FormattedText([("bold", f"{cwd} {symbol} ")])

    def _render_bottom_toolbar(self) -> FormattedText:
        info = self._last_tape_info
        now = datetime.now().strftime("%H:%M")
        left = f"{now}  mode:{self._mode}"
        right = (
            f"model:{self.runtime.settings.model}  "
            f"entries:{getattr(info, 'entries', '-')} "
            f"anchors:{getattr(info, 'anchors', '-')} "
            f"last:{getattr(info, 'last_anchor', None) or '-'}"
        )
        return FormattedText([("", f"{left}  {right}")])

    def _normalize_input(self, raw: str) -> str:
        if self._mode != "shell":
            return raw
        if raw.startswith(","):
            return raw
        return f", {raw}"

    @staticmethod
    def _history_file(home: Path, workspace: Path) -> Path:
        workspace_hash = md5(str(workspace).encode("utf-8")).hexdigest()  # noqa: S324
        return home / "history" / f"{workspace_hash}.history"
