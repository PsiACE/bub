"""Interactive CLI implementation."""

from __future__ import annotations

from datetime import datetime
from hashlib import md5
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich import get_console

from bub.app.runtime import AppRuntime
from bub.cli.render import CliRenderer


class InteractiveCli:
    """Single interactive CLI mode inspired by modern coding agent shells."""

    def __init__(self, runtime: AppRuntime, *, session_id: str = "cli") -> None:
        self._runtime = runtime
        self._session_id = session_id
        self._session = runtime.get_session(session_id)
        self._renderer = CliRenderer(get_console())
        self._mode = "agent"
        self._prompt = self._build_prompt()

    async def run(self) -> None:
        self._renderer.welcome(model=self._runtime.settings.model, workspace=str(self._runtime.workspace))
        while True:
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
                result = await self._runtime.handle_input(self._session_id, request)
            if result.immediate_output:
                self._renderer.command_output(result.immediate_output)
            if result.error:
                self._renderer.error(result.error)
            if result.assistant_output:
                self._renderer.assistant_output(result.assistant_output)
            if result.exit_requested:
                break
        self._renderer.info("Bye.")

    def _build_prompt(self) -> PromptSession[str]:
        kb = KeyBindings()

        @kb.add("c-x", eager=True)
        def _toggle_mode(event) -> None:
            self._mode = "shell" if self._mode == "agent" else "agent"
            event.app.invalidate()

        history_file = self._history_file(self._runtime.settings.resolve_home(), self._runtime.workspace)
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_file))
        completer = WordCompleter(
            [
                ",help",
                ",tools",
                ",tool.describe",
                ",tape.info",
                ",tape.search",
                ",anchors",
                ",handoff",
                ",skills.list",
                ",skills.describe",
                ",quit",
            ],
            ignore_case=True,
        )
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
        info = self._session.tape.info()
        now = datetime.now().strftime("%H:%M")
        left = f"{now}  mode:{self._mode}"
        right = (
            f"model:{self._runtime.settings.model}  "
            f"entries:{info.entries} anchors:{info.anchors} last:{info.last_anchor or '-'}"
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
