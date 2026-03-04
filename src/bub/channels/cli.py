"""CLI channel adapter."""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import md5
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.patch_stdout import patch_stdout
from rich import get_console

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel, exclude_none
from bub.channels.media import MAX_INLINE_IMAGE_BYTES, guess_image_mime, to_data_url
from bub.cli.render import CliRenderer
from bub.core.agent_loop import LoopResult

CLIPBOARD_PLACEHOLDER_RE = re.compile(
    r"\[(?P<type>image):(?P<id>[a-zA-Z0-9_\-\.]+)(?:,(?P<width>\d+)x(?P<height>\d+))?\]"
)
LOCAL_IMAGE_TOKEN_RE = re.compile(r"(?<!\S)@(?P<path>\"[^\"]+\"|'[^']+'|[^\s]+)")


@dataclass(frozen=True)
class InlineImage:
    id: str
    data_url: str
    mime_type: str
    file_size: int
    width: int | None = None
    height: int | None = None
    path: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return exclude_none({
            "id": self.id,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "path": self.path,
            "data_url": self.data_url,
        })


@dataclass(frozen=True)
class CliInput:
    text: str
    images: tuple[InlineImage, ...] = ()


class CliChannel(BaseChannel[CliInput]):
    """Interactive terminal channel."""

    name = "cli"
    INLINE_IMAGE_LIMIT_BYTES = MAX_INLINE_IMAGE_BYTES

    def __init__(self, runtime: AppRuntime, *, session_id: str = "cli") -> None:
        super().__init__(runtime)
        self._session_id = session_id
        self._session = runtime.get_session(session_id)
        self._renderer = CliRenderer(get_console())
        self._mode = "agent"
        self._last_tape_info: object | None = None
        self._prompt = self._build_prompt()
        self._stop_requested = False
        self._clipboard_images: dict[str, InlineImage] = {}
        self._missing_pillow_reported = False

    @property
    def debounce_enabled(self) -> bool:
        return False

    async def start(self, on_receive: Callable[[CliInput], Awaitable[None]]) -> None:
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
            payload, notices = self._build_cli_input(request)
            for notice in notices:
                self._renderer.info(notice)
            with self._renderer.console.status("[cyan]Processing...[/cyan]", spinner="dots"):
                await on_receive(payload)

        self._renderer.info("Bye.")

    def is_mentioned(self, message: CliInput) -> bool:
        _ = message
        return True

    async def get_session_prompt(self, message: CliInput) -> tuple[str, str]:
        if not message.images:
            return self._session_id, message.text

        content = message.text.strip() or "[Image input]"
        prompt = json.dumps(
            {
                "message": content,
                "source": "cli",
                "media": {"images": [image.to_metadata() for image in message.images]},
            },
            ensure_ascii=False,
        )
        return self._session_id, prompt

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

        @kb.add("c-v", eager=True)
        def _paste(event: KeyPressEvent) -> None:
            if self._try_paste_image(event):
                return
            clipboard_data = event.app.clipboard.get_data()
            event.current_buffer.paste_clipboard_data(clipboard_data)

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

    def _build_cli_input(self, request: str) -> tuple[CliInput, list[str]]:
        if request.lstrip().startswith(","):
            self._clipboard_images.clear()
            return CliInput(text=request), []

        extracted_images: list[InlineImage] = []
        notices: list[str] = []
        text = request
        text, clipboard_images = self._extract_clipboard_images(text)
        extracted_images.extend(clipboard_images)
        text, path_images, path_notices = self._extract_local_path_images(text)
        extracted_images.extend(path_images)
        notices.extend(path_notices)

        self._clipboard_images.clear()
        normalized_text = text.strip()
        return CliInput(text=normalized_text, images=tuple(extracted_images)), notices

    def _extract_clipboard_images(self, text: str) -> tuple[str, list[InlineImage]]:
        images: list[InlineImage] = []
        chunks: list[str] = []
        last = 0
        for match in CLIPBOARD_PLACEHOLDER_RE.finditer(text):
            attachment_id = match.group("id")
            image = self._clipboard_images.pop(attachment_id, None)
            if image is None:
                continue
            chunks.append(text[last : match.start()])
            last = match.end()
            images.append(image)
        chunks.append(text[last:])
        return "".join(chunks), images

    def _extract_local_path_images(self, text: str) -> tuple[str, list[InlineImage], list[str]]:
        images: list[InlineImage] = []
        notices: list[str] = []
        chunks: list[str] = []
        last = 0

        for match in LOCAL_IMAGE_TOKEN_RE.finditer(text):
            raw_path = self._normalize_path_token(match.group("path"))
            loaded, notice = self._load_local_image(raw_path)
            if loaded is None:
                continue
            chunks.append(text[last : match.start()])
            last = match.end()
            images.append(loaded)
            if notice:
                notices.append(notice)

        chunks.append(text[last:])
        return "".join(chunks), images, notices

    def _load_local_image(self, raw_path: str) -> tuple[InlineImage | None, str | None]:
        candidate = Path(raw_path).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (self.runtime.workspace / candidate).resolve()

        try:
            if not resolved.is_file():
                return None, None
        except OSError:
            logger.exception("cli.local_image.invalid_path path={}", raw_path)
            return None, f"Failed to read image path: {raw_path}"

        mime_type = guess_image_mime(None, resolved.name)
        if mime_type is None:
            return None, None

        try:
            payload = resolved.read_bytes()
        except OSError:
            logger.exception("cli.local_image.read_error path={}", str(resolved))
            return None, f"Failed to read image: {resolved}"

        if not payload:
            return None, f"Skipped empty image file: {resolved}"
        if len(payload) > self.INLINE_IMAGE_LIMIT_BYTES:
            return None, (f"Skipped image larger than {self.INLINE_IMAGE_LIMIT_BYTES // (1024 * 1024)}MB: {resolved}")

        width, height = self._try_detect_dimensions(payload)
        image = InlineImage(
            id=f"{uuid4().hex[:8]}{resolved.suffix}",
            data_url=to_data_url(payload, mime_type),
            mime_type=mime_type,
            file_size=len(payload),
            width=width,
            height=height,
            path=str(resolved),
        )
        return image, f"Attached image: {resolved}"

    @staticmethod
    def _normalize_path_token(raw: str) -> str:
        if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
            return raw[1:-1]
        return raw

    @staticmethod
    def _try_detect_dimensions(payload: bytes) -> tuple[int | None, int | None]:
        try:
            from PIL import Image
        except Exception:
            return None, None

        with contextlib.suppress(Exception), Image.open(BytesIO(payload)) as image:
            return image.width, image.height
        return None, None

    def _try_paste_image(self, event: KeyPressEvent) -> bool:
        try:
            from PIL import Image, ImageGrab
        except ModuleNotFoundError as exc:
            if exc.name == "PIL" and not self._missing_pillow_reported:
                self._renderer.info("Install `pillow` to enable clipboard image paste.")
                self._missing_pillow_reported = True
            return False
        except Exception as exc:
            logger.debug("cli.clipboard_image.import_failed error={}", exc)
            return False

        with contextlib.suppress(Exception):
            image = ImageGrab.grabclipboard()
            if image is None:
                return False

            if not isinstance(image, Image.Image):
                for item in image:
                    try:
                        with Image.open(item) as loaded:
                            image = loaded.copy()
                        break
                    except Exception as exc:
                        logger.debug("cli.clipboard_image.open_candidate_failed candidate={} error={}", item, exc)
                else:
                    return False

            output = BytesIO()
            image.save(output, format="PNG")
            payload = output.getvalue()
            if len(payload) > self.INLINE_IMAGE_LIMIT_BYTES:
                self._renderer.info(
                    f"Skipped pasted image larger than {self.INLINE_IMAGE_LIMIT_BYTES // (1024 * 1024)}MB."
                )
                return False

            image_id = f"{uuid4().hex[:8]}.png"
            inline_image = InlineImage(
                id=image_id,
                data_url=to_data_url(payload, "image/png"),
                mime_type="image/png",
                file_size=len(payload),
                width=image.width,
                height=image.height,
            )
            self._clipboard_images[image_id] = inline_image
            placeholder = f"[image:{image_id},{image.width}x{image.height}]"
            event.current_buffer.insert_text(placeholder)
            event.app.invalidate()
            logger.info("cli.clipboard_image.attached id={} size={}x{}", image_id, image.width, image.height)
            return True
        return False

    @staticmethod
    def _history_file(home: Path, workspace: Path) -> Path:
        workspace_hash = md5(str(workspace).encode("utf-8")).hexdigest()  # noqa: S324
        return home / "history" / f"{workspace_hash}.history"
