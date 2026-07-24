"""Response-scoped Markdown buffering for CLI streaming output."""

from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text

_MARKDOWN_CODE_THEME = "ansi_dark"


def _markdown(content: str) -> Markdown:
    return Markdown(content, code_theme=_MARKDOWN_CODE_THEME)


class MarkdownWriter:
    """Keep one response segment as a single Markdown document.

    Newlines are Markdown structure, not terminal commit boundaries. The
    buffer is drained only at an explicit model or tool boundary.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def append(self, text: str) -> None:
        self._buffer += text

    def render_live(self) -> Markdown | Text:
        if not self._buffer.strip():
            return Text("")
        return _markdown(self._buffer)

    def render_final(self) -> Markdown | None:
        if not self._buffer.strip():
            return None
        return _markdown(self._buffer.rstrip())

    def clear(self) -> None:
        self._buffer = ""

    def has_content(self) -> bool:
        return bool(self._buffer.strip())
