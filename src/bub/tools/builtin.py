"""Built-in tool definitions."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field
from republic import Tool, tool_from_model

from bub.skills.loader import SkillMetadata
from bub.tape.service import TapeService
from bub.tools.registry import ToolDescriptor, ToolRegistry


class BashInput(BaseModel):
    cmd: str = Field(..., description="Shell command")
    cwd: str | None = Field(default=None, description="Working directory")


class ReadInput(BaseModel):
    path: str = Field(..., description="File path")
    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(default=None, ge=1)


class WriteInput(BaseModel):
    path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")


class EditInput(BaseModel):
    path: str = Field(..., description="File path")
    old: str = Field(..., description="Search text")
    new: str = Field(..., description="Replacement text")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class GlobInput(BaseModel):
    pattern: str = Field(..., description="Glob pattern")
    path: str = Field(default=".", description="Base path")


class GrepInput(BaseModel):
    pattern: str = Field(..., description="Substring pattern")
    path: str = Field(default=".", description="Base path")


class FetchInput(BaseModel):
    url: str = Field(..., description="URL")


class SearchInput(BaseModel):
    query: str = Field(..., description="Search query")


class HandoffInput(BaseModel):
    name: str | None = Field(default=None, description="Anchor name")
    summary: str | None = Field(default=None, description="Summary")
    next_steps: str | None = Field(default=None, description="Next steps")


class ToolNameInput(BaseModel):
    name: str = Field(..., description="Tool name")


class TapeSearchInput(BaseModel):
    query: str = Field(..., description="Query")
    limit: int = Field(default=20, ge=1)


class TapeResetInput(BaseModel):
    archive: bool = Field(default=False)


class SkillNameInput(BaseModel):
    name: str = Field(..., description="Skill name")


class EmptyInput(BaseModel):
    pass


def _resolve_path(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return workspace / path


def register_builtin_tools(
    registry: ToolRegistry,
    *,
    workspace: Path,
    tape: TapeService,
    skills: list[SkillMetadata],
    load_skill_body: Callable[[str], str | None],
) -> None:
    """Register built-in tools and internal commands."""

    def run_bash(params: BashInput) -> str:
        cwd = params.cwd or str(workspace)
        executable = shutil.which("bash") or "bash"
        completed = subprocess.run(  # noqa: S603
            [executable, "-lc", params.cmd],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            message = stderr or stdout or f"exit={completed.returncode}"
            raise RuntimeError(f"exit={completed.returncode}: {message}")
        return stdout or "(no output)"

    def fs_read(params: ReadInput) -> str:
        file_path = _resolve_path(workspace, params.path)
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = min(params.offset, len(lines))
        end = len(lines) if params.limit is None else min(len(lines), start + params.limit)
        return "\n".join(lines[start:end])

    def fs_write(params: WriteInput) -> str:
        file_path = _resolve_path(workspace, params.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(params.content, encoding="utf-8")
        return f"wrote: {file_path}"

    def fs_edit(params: EditInput) -> str:
        file_path = _resolve_path(workspace, params.path)
        text = file_path.read_text(encoding="utf-8")
        if params.replace_all:
            count = text.count(params.old)
            if count == 0:
                raise RuntimeError("old text not found")
            updated = text.replace(params.old, params.new)
            file_path.write_text(updated, encoding="utf-8")
            return f"updated: {file_path} occurrences={count}"

        if params.old not in text:
            raise RuntimeError("old text not found")
        updated = text.replace(params.old, params.new, 1)
        file_path.write_text(updated, encoding="utf-8")
        return f"updated: {file_path} occurrences=1"

    def fs_glob(params: GlobInput) -> str:
        base = _resolve_path(workspace, params.path)
        matches = sorted(base.glob(params.pattern))
        return "\n".join(str(path) for path in matches) or "(no matches)"

    def fs_grep(params: GrepInput) -> str:
        base = _resolve_path(workspace, params.path)
        rows: list[str] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for idx, line in enumerate(content.splitlines(), start=1):
                if params.pattern in line:
                    rows.append(f"{path}:{idx}:{line}")
        return "\n".join(rows) if rows else "(no matches)"

    def web_fetch(params: FetchInput) -> str:
        request = Request(params.url, headers={"User-Agent": "bub/0.2"})  # noqa: S310
        with urlopen(request, timeout=20) as response:  # noqa: S310
            body: bytes = response.read(80_000)
            return body.decode("utf-8", errors="replace")

    def web_search(params: SearchInput) -> str:
        query = quote_plus(params.query)
        return f"https://duckduckgo.com/?q={query}"

    def command_help(_params: EmptyInput) -> str:
        return (
            "Commands use ',' at line start.\n"
            "Known names map to internal tools; other commands run through bash.\n"
            "Examples:\n"
            "  ,help\n"
            "  ,git status\n"
            "  , ls -la\n"
            "  ,tools\n"
            "  ,tool.describe name=fs.read\n"
            "  ,handoff name=phase-1 summary='Bootstrap complete'\n"
            "  ,anchors\n"
            "  ,tape.info\n"
            "  ,tape.search query=error\n"
            "  ,skills.list\n"
            "  ,skills.describe name=friendly-python\n"
            "  ,quit\n"
        )

    def list_tools(_params: EmptyInput) -> str:
        return "\n".join(registry.compact_rows())

    def tool_describe(params: ToolNameInput) -> str:
        return registry.detail(params.name)

    def handoff(params: HandoffInput) -> str:
        anchor_name = params.name or "handoff"
        state: dict[str, object] = {}
        if params.summary:
            state["summary"] = params.summary
        if params.next_steps:
            state["next_steps"] = params.next_steps
        tape.handoff(anchor_name, state=state or None)
        return f"handoff created: {anchor_name}"

    def anchors(_params: EmptyInput) -> str:
        rows = []
        for anchor in tape.anchors(limit=50):
            rows.append(f"{anchor.name} state={json.dumps(anchor.state, ensure_ascii=False)}")
        return "\n".join(rows) if rows else "(no anchors)"

    def tape_info(_params: EmptyInput) -> str:
        info = tape.info()
        return f"tape={info.name} entries={info.entries} anchors={info.anchors} last_anchor={info.last_anchor or '-'}"

    def tape_search(params: TapeSearchInput) -> str:
        entries = tape.search(params.query, limit=params.limit)
        if not entries:
            return "(no matches)"
        return "\n".join(f"#{entry.id} {entry.kind} {entry.payload}" for entry in entries)

    def tape_reset(params: TapeResetInput) -> str:
        return tape.reset(archive=params.archive)

    def list_skills(_params: EmptyInput) -> str:
        if not skills:
            return "(no skills)"
        return "\n".join(f"{skill.name}: {skill.description}" for skill in skills)

    def describe_skill(params: SkillNameInput) -> str:
        body = load_skill_body(params.name)
        if not body:
            raise RuntimeError(f"skill not found: {params.name}")
        return body

    def quit_command(_params: EmptyInput) -> str:
        return "exit"

    tool_specs: list[tuple[Tool, str, str]] = [
        (
            tool_from_model(BashInput, run_bash, name="bash", description="Run a shell command."),
            "Run shell command",
            "Execute bash in workspace. Non-zero exit raises an error.",
        ),
        (
            tool_from_model(ReadInput, fs_read, name="fs.read", description="Read file content."),
            "Read file",
            "Read UTF-8 text with optional offset and limit.",
        ),
        (
            tool_from_model(WriteInput, fs_write, name="fs.write", description="Write file content."),
            "Write file",
            "Write UTF-8 text to path, creating parent directory if needed.",
        ),
        (
            tool_from_model(EditInput, fs_edit, name="fs.edit", description="Replace file text."),
            "Edit file",
            "Replace one or all occurrences of old text in file.",
        ),
        (
            tool_from_model(GlobInput, fs_glob, name="fs.glob", description="Find files by glob."),
            "Find files",
            "Glob files under a base path.",
        ),
        (
            tool_from_model(GrepInput, fs_grep, name="fs.grep", description="Search files by substring."),
            "Search files",
            "Scan files recursively and return matching lines.",
        ),
        (
            tool_from_model(FetchInput, web_fetch, name="web.fetch", description="Fetch URL content."),
            "Fetch URL",
            "Fetch raw response body from URL.",
        ),
        (
            tool_from_model(SearchInput, web_search, name="web.search", description="Build web search URL."),
            "Search web",
            "Return a DuckDuckGo search URL for the query.",
        ),
        (
            tool_from_model(EmptyInput, command_help, name="help", description="Show command help."),
            "Show help",
            "Show Bub internal command usage and examples.",
        ),
        (
            tool_from_model(EmptyInput, list_tools, name="tools", description="List available tools."),
            "List tools",
            "List all tools in compact mode.",
        ),
        (
            tool_from_model(ToolNameInput, tool_describe, name="tool.describe", description="Show tool detail."),
            "Describe tool",
            "Expand one tool description and schema.",
        ),
        (
            tool_from_model(HandoffInput, handoff, name="handoff", description="Create anchor handoff."),
            "Create handoff",
            "Create tape anchor with optional summary and next_steps state.",
        ),
        (
            tool_from_model(EmptyInput, anchors, name="anchors", description="List anchors."),
            "List anchors",
            "List recent tape anchors.",
        ),
        (
            tool_from_model(EmptyInput, tape_info, name="tape.info", description="Show tape summary."),
            "Tape info",
            "Show tape summary with entry and anchor counts.",
        ),
        (
            tool_from_model(TapeSearchInput, tape_search, name="tape.search", description="Search tape entries."),
            "Search tape",
            "Search entries in tape by query.",
        ),
        (
            tool_from_model(TapeResetInput, tape_reset, name="tape.reset", description="Reset tape entries."),
            "Reset tape",
            "Reset current tape; can archive before clearing.",
        ),
        (
            tool_from_model(EmptyInput, list_skills, name="skills.list", description="List available skills."),
            "List skills",
            "List all discovered skills in compact form.",
        ),
        (
            tool_from_model(SkillNameInput, describe_skill, name="skills.describe", description="Load one skill body."),
            "Describe skill",
            "Load full SKILL.md body for one skill name.",
        ),
        (
            tool_from_model(EmptyInput, quit_command, name="quit", description="Quit interactive session."),
            "Quit session",
            "Request exit from interactive CLI.",
        ),
    ]

    for tool, short, detail in tool_specs:
        registry.register(
            ToolDescriptor(
                name=tool.name,
                short_description=short,
                detail=detail,
                tool=tool,
                source="builtin",
            )
        )

    for skill in skills:
        tool_name = f"skill.{skill.name}"
        if registry.has(tool_name):
            continue

        def _skill_handler(_params: EmptyInput, *, skill_name: str = skill.name) -> str:
            body = load_skill_body(skill_name)
            if not body:
                raise RuntimeError(f"skill not found: {skill_name}")
            return body

        skill_tool = tool_from_model(
            EmptyInput,
            _skill_handler,
            name=tool_name,
            description=f"Load skill content for {skill.name}.",
        )
        registry.register(
            ToolDescriptor(
                name=skill_tool.name,
                short_description=skill.description,
                detail=f"Load full SKILL.md for {skill.name}.",
                tool=skill_tool,
                source="skill",
            )
        )


def shell_cmd_from_tokens(tokens: list[str]) -> str:
    """Return shell command string preserving token quoting."""

    return " ".join(shlex.quote(token) for token in tokens)
