"""Filesystem tool factories."""

from __future__ import annotations

import re
from pathlib import Path

from republic import Tool, tool_from_model

from ...agent.context import Context
from .shared import EditInput, GlobInput, GrepInput, ReadInput, WriteInput, resolve_path

MAX_GREP_MATCHES = 50


def create_read_tool(context: Context) -> Tool:
    """Create the read tool bound to the workspace context."""

    def _handler(params: ReadInput) -> str:
        file_path = resolve_path(context, params.path)
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            return f"error: {exc!s}"

        offset = max(params.offset, 0)
        limit = len(lines) if params.limit is None else max(params.limit, 0)
        selected = lines[offset : offset + limit]
        return "\n".join(f"{idx:4}| {line}" for idx, line in enumerate(selected, start=offset + 1))

    return tool_from_model(
        ReadInput,
        _handler,
        name="fs.read",
        description="Read a file with optional offset and limit",
    )


def create_write_tool(context: Context) -> Tool:
    """Create the write tool bound to the workspace context."""

    def _handler(params: WriteInput) -> str:
        file_path = resolve_path(context, params.path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(params.content, encoding="utf-8")
        except OSError as exc:
            return f"error: {exc!s}"
        return "ok"

    return tool_from_model(
        WriteInput,
        _handler,
        name="fs.write",
        description="Write content to a file",
    )


def create_edit_tool(context: Context) -> Tool:
    """Create the edit tool bound to the workspace context."""

    def _handler(params: EditInput) -> str:
        file_path = resolve_path(context, params.path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return f"error: {exc!s}"

        if params.old not in content:
            return "error: old_string not found"

        count = content.count(params.old)
        if count > 1 and not params.all:
            return f"error: old_string appears {count} times, must be unique (use all=true)"

        updated = content.replace(params.old, params.new) if params.all else content.replace(params.old, params.new, 1)
        try:
            file_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return f"error: {exc!s}"
        return "ok"

    return tool_from_model(
        EditInput,
        _handler,
        name="fs.edit",
        description="Replace text in a file",
    )


def create_glob_tool(context: Context) -> Tool:
    """Create the glob tool bound to the workspace context."""

    def _handler(params: GlobInput) -> str:
        base = resolve_path(context, params.path)
        try:
            matches = list(base.glob(params.pattern))
        except OSError as exc:
            return f"error: {exc!s}"

        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        matches.sort(key=_mtime, reverse=True)
        if not matches:
            return "none"
        return "\n".join(str(path) for path in matches)

    return tool_from_model(
        GlobInput,
        _handler,
        name="fs.glob",
        description="Find files matching a glob pattern",
    )


def create_grep_tool(context: Context) -> Tool:
    """Create the grep tool bound to the workspace context."""

    def _handler(params: GrepInput) -> str:
        base = resolve_path(context, params.path)
        try:
            regex = re.compile(params.pattern)
        except re.error as exc:
            return f"error: {exc!s}"

        matches: list[str] = []
        for file_path in base.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{file_path}:{idx}:{line}")
                    if len(matches) >= MAX_GREP_MATCHES:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "none"

    return tool_from_model(
        GrepInput,
        _handler,
        name="fs.grep",
        description="Search for a regex pattern in files",
    )
