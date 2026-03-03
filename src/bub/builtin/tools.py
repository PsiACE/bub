from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from republic import ToolContext, tool

if TYPE_CHECKING:
    from bub.builtin.engine import RuntimeEngine

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30


def _get_runtime(context: ToolContext) -> RuntimeEngine:
    if "_runtime_engine" not in context.state:
        raise RuntimeError("no runtime engine found in tool context")
    return cast("RuntimeEngine", context.state["_runtime_engine"])


@tool(context=True)
async def bash(
    cmd: str, cwd: str | None = None, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS, *, context: ToolContext
) -> str:
    """Run a shell command and return its output within a time limit. Raises if the command fails or times out."""
    workspace = context.state.get("_runtime_workspace")
    completed = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        cmd,
        cwd=cwd or workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    async with asyncio.timeout(timeout_seconds):
        stdout_bytes, stderr_bytes = await completed.communicate()
    stdout_text = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
    stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
    if completed.returncode != 0:
        message = stderr_text or stdout_text or f"exit={completed.returncode}"
        raise RuntimeError(f"exit={completed.returncode}: {message}")
    return stdout_text or "(no output)"


@tool(context=True)
def fs_read(path: str, offset: int = 0, limit: int | None = None, *, context: ToolContext) -> str:
    """Read a text file and return its content. Supports optional pagination with offset and limit."""
    resolved_path = _resolve_path(context, path)
    text = resolved_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = max(0, min(offset, len(lines)))
    end = len(lines) if limit is None else min(len(lines), start + max(0, limit))
    return "\n".join(lines[start:end])


@tool(context=True)
def fs_write(path: str, content: str, *, context: ToolContext) -> str:
    """Write content to a text file."""
    resolved_path = _resolve_path(context, path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content, encoding="utf-8")
    return f"wrote: {resolved_path}"


@tool(context=True)
def fs_edit(path: str, old: str, new: str, start: int = 0, *, context: ToolContext) -> str:
    """Edit a text file by replacing old text with new text. You can specify the line number to start searching for the old text."""
    resolved_path = _resolve_path(context, path)
    text = resolved_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    prev, to_replace = "\n".join(lines[:start]), "\n".join(lines[start:])
    if old not in to_replace:
        raise ValueError(f"'{old}' not found in {resolved_path} from line {start}")
    replaced = to_replace.replace(old, new)
    resolved_path.write_text(prev + "\n" + replaced, encoding="utf-8")
    return f"edited: {resolved_path}"


@tool(context=True)
async def tape_info(context: ToolContext) -> str:
    runtime = _get_runtime(context)
    info = await runtime.tapes.info(context.tape or "")
    return f"name: {info.name}\nentries: {info.entries}\nanchors: {info.anchors}\nlast_anchor: {info.last_anchor}"


@tool(context=True)
async def tape_search(query: str, limit: int = 20, *, context: ToolContext) -> str:
    runtime = _get_runtime(context)
    entries = await runtime.tapes.search(context.tape or "", query=query, limit=limit)
    if not entries:
        return "(no matches)"
    return "\n".join(f"- {json.dumps(entry.payload)}" for entry in entries)


@tool(context=True)
async def tape_reset(archive: bool = False, *, context: ToolContext) -> str:
    runtime = _get_runtime(context)
    result = await runtime.tapes.reset(context.tape or "", archive=archive)
    return result


@tool(context=True)
async def tape_handoff(name: str = "handoff", summary: str = "", *, context: ToolContext) -> str:
    runtime = _get_runtime(context)
    await runtime.tapes.handoff(context.tape or "", name=name, state={"summary": summary})
    return f"anchor added: {name}"


@tool(context=True)
async def tape_anchors(*, context: ToolContext) -> str:
    runtime = _get_runtime(context)
    anchors = await runtime.tapes.anchors(context.tape or "")
    if not anchors:
        return "(no anchors)"
    return "\n".join(f"- {anchor.name}" for anchor in anchors)


@tool(name="help")
def show_help() -> str:
    """List available tools."""
    return (
        "Commands use ',' at line start.\n"
        "Known internal commands:\n"
        "  ,help\n"
        "  ,tape.info\n"
        "  ,tape.search query=error\n"
        "  ,tape.handoff name=phase-1 summary='done'\n"
        "  ,tape.anchors\n"
        "  ,fs.read path=README.md\n"
        "  ,fs.write path=tmp.txt content='hello'\n"
        "  ,fs.edit path=tmp.txt old=hello new=world\n"
        "Any unknown command after ',' is executed as shell via bash."
    )


def _resolve_path(context: ToolContext, raw_path: str) -> Path:
    workspace = context.state.get("_runtime_workspace")
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    if workspace is None:
        raise ValueError(f"relative path '{raw_path}' is not allowed without a workspace")
    return (workspace / path).resolve()
