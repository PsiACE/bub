from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from republic import Tool, ToolContext

from bub.skills import discover_skills
from bub.tools import tool

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


@tool(context=True, name="fs.read")
def fs_read(path: str, offset: int = 0, limit: int | None = None, *, context: ToolContext) -> str:
    """Read a text file and return its content. Supports optional pagination with offset and limit."""
    resolved_path = _resolve_path(context, path)
    text = resolved_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = max(0, min(offset, len(lines)))
    end = len(lines) if limit is None else min(len(lines), start + max(0, limit))
    return "\n".join(lines[start:end])


@tool(context=True, name="fs.write")
def fs_write(path: str, content: str, *, context: ToolContext) -> str:
    """Write content to a text file."""
    resolved_path = _resolve_path(context, path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content, encoding="utf-8")
    return f"wrote: {resolved_path}"


@tool(context=True, name="fs.edit")
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


@tool(context=True, name="skill.load")
def skill_load(name: str, *, context: ToolContext) -> str:
    """Load the skill content by name. The skill must be located in predefined locations and have a valid frontmatter."""
    from bub.builtin.engine import workspace_from_state

    workspace = workspace_from_state(context.state)
    skill_index = {skill.name: skill for skill in discover_skills(workspace)}
    if name.casefold() not in skill_index:
        return "(no such skill)"
    skill = skill_index[name.casefold()]
    return skill.body() or "(skill has no body)"


@tool(context=True, name="tape.info")
async def tape_info(context: ToolContext) -> str:
    """Get information about the current tape, such as number of entries and anchors."""
    runtime = _get_runtime(context)
    info = await runtime.tapes.info(context.tape or "")
    return (
        f"name: {info.name}\n"
        f"entries: {info.entries}\n"
        f"anchors: {info.anchors}\n"
        f"last_anchor: {info.last_anchor}\n"
        f"entries_since_last_anchor: {info.entries_since_last_anchor}\n"
        f"last_token_usage: {info.last_token_usage}"
    )


@tool(context=True, name="tape.search")
async def tape_search(query: str, limit: int = 20, *, context: ToolContext) -> str:
    """Search for entries in the current tape that match the query. Returns a list of matching entries."""
    runtime = _get_runtime(context)
    entries = await runtime.tapes.search(context.tape or "", query=query, limit=limit)
    if not entries:
        return "(no matches)"
    return "\n".join(f"- {json.dumps(entry.payload)}" for entry in entries)


@tool(context=True, name="tape.reset")
async def tape_reset(archive: bool = False, *, context: ToolContext) -> str:
    """Reset the current tape, optionally archiving it."""
    runtime = _get_runtime(context)
    result = await runtime.tapes.reset(context.tape or "", archive=archive)
    return result


@tool(context=True, name="tape.handoff")
async def tape_handoff(name: str = "handoff", summary: str = "", *, context: ToolContext) -> str:
    """Add a handoff anchor to the current tape."""
    runtime = _get_runtime(context)
    await runtime.tapes.handoff(context.tape or "", name=name, state={"summary": summary})
    return f"anchor added: {name}"


@tool(context=True, name="tape.anchors")
async def tape_anchors(*, context: ToolContext) -> str:
    """List anchors in the current tape."""
    runtime = _get_runtime(context)
    anchors = await runtime.tapes.anchors(context.tape or "")
    if not anchors:
        return "(no anchors)"
    return "\n".join(f"- {anchor.name}" for anchor in anchors)


@tool(name="help")
def show_help() -> str:
    """Show a help message."""
    return (
        "Commands use ',' at line start.\n"
        "Known internal commands:\n"
        "  ,help\n"
        "  ,skill.load name=foo\n"
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
    if not isinstance(workspace, str | Path):
        raise TypeError("runtime workspace must be a filesystem path")
    workspace_path = Path(workspace)
    return (workspace_path / path).resolve()


def get_builtin_tools() -> list[Tool]:
    return [
        show_help,
        bash,
        skill_load,
        fs_read,
        fs_write,
        fs_edit,
        tape_info,
        tape_search,
        tape_reset,
        tape_handoff,
        tape_anchors,
    ]
