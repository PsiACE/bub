"""Built-in tool definitions."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib.request import Request, urlopen

import html2markdown
from pydantic import BaseModel, Field
from republic import Tool, tool_from_model

from bub.config.settings import Settings
from bub.skills.loader import SkillMetadata
from bub.tape.service import TapeService
from bub.tools.registry import ToolDescriptor, ToolRegistry

DEFAULT_OLLAMA_WEB_API_BASE = "https://ollama.com/api"
WEB_REQUEST_TIMEOUT_SECONDS = 20
MAX_FETCH_BYTES = 1_000_000
WEB_USER_AGENT = "bub-web-tools/1.0"


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
    max_results: int = Field(default=5, ge=1, le=10)


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


def _normalize_url(raw_url: str) -> str | None:
    normalized = raw_url.strip()
    if not normalized:
        return None

    parsed = urllib_parse.urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            return None
        return normalized

    if parsed.scheme == "" and parsed.netloc == "" and parsed.path:
        with_scheme = f"https://{normalized}"
        parsed = urllib_parse.urlparse(with_scheme)
        if parsed.netloc:
            return with_scheme

    return None


def _normalize_api_base(raw_api_base: str) -> str | None:
    normalized = raw_api_base.strip().rstrip("/")
    if not normalized:
        return None

    parsed = urllib_parse.urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized
    return None


def _html_to_markdown(content: str) -> str:
    rendered = html2markdown.convert(content)
    lines = [line.rstrip() for line in rendered.splitlines()]
    return "\n".join(line for line in lines if line.strip())


def _format_search_results(results: list[object]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "(untitled)")
        url = str(item.get("url") or "")
        content = str(item.get("content") or "")
        lines.append(f"{idx}. {title}")
        if url:
            lines.append(f"   {url}")
        if content:
            lines.append(f"   {content}")
    return "\n".join(lines) if lines else "none"


def register_builtin_tools(
    registry: ToolRegistry,
    *,
    workspace: Path,
    tape: TapeService,
    skills: list[SkillMetadata],
    load_skill_body: Callable[[str], str | None],
    settings: Settings,
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
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(content.splitlines(), start=1):
                if params.pattern in line:
                    rows.append(f"{path}:{idx}:{line}")
        return "\n".join(rows) if rows else "(no matches)"

    def _fetch_markdown_from_url(raw_url: str) -> str:
        url = _normalize_url(raw_url)
        if not url:
            return "error: invalid url"

        request = Request(  # noqa: S310
            url,
            headers={
                "User-Agent": WEB_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urlopen(request, timeout=WEB_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                body_bytes = response.read(MAX_FETCH_BYTES + 1)
                truncated = len(body_bytes) > MAX_FETCH_BYTES
                if truncated:
                    body_bytes = body_bytes[:MAX_FETCH_BYTES]
                charset = response.headers.get_content_charset() or "utf-8"
        except urllib_error.URLError as exc:
            return f"error: {exc!s}"
        except OSError as exc:
            return f"error: {exc!s}"

        content = body_bytes.decode(charset, errors="replace")
        rendered = _html_to_markdown(content).strip()
        if not rendered:
            return "error: empty response body"
        if truncated:
            return f"{rendered}\n\n[truncated: response exceeded byte limit]"
        return rendered

    def web_fetch_default(params: FetchInput) -> str:
        return _fetch_markdown_from_url(params.url)

    def web_search_default(params: SearchInput) -> str:
        query = urllib_parse.quote_plus(params.query)
        return f"https://duckduckgo.com/?q={query}"

    def web_fetch_ollama(params: FetchInput) -> str:
        return _fetch_markdown_from_url(params.url)

    def web_search_ollama(params: SearchInput) -> str:
        api_key = settings.ollama_api_key
        if not api_key:
            return "error: ollama api key is not configured"

        api_base = _normalize_api_base(settings.ollama_api_base or DEFAULT_OLLAMA_WEB_API_BASE)
        if not api_base:
            return "error: invalid ollama api base url"

        endpoint = f"{api_base}/web_search"
        payload = {
            "query": params.query,
            "max_results": params.max_results,
        }
        request = Request(  # noqa: S310
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": WEB_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=WEB_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                response_body = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            if detail:
                return f"error: http {exc.code}: {detail}"
            return f"error: http {exc.code}"
        except urllib_error.URLError as exc:
            return f"error: {exc!s}"
        except OSError as exc:
            return f"error: {exc!s}"

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            return f"error: invalid json response: {exc!s}"

        results = data.get("results")
        if not isinstance(results, list) or not results:
            return "none"
        return _format_search_results(results)

    use_ollama_web_tools = bool(settings.ollama_api_key)
    web_fetch_handler = web_fetch_ollama if use_ollama_web_tools else web_fetch_default
    web_search_handler = web_search_ollama if use_ollama_web_tools else web_search_default

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
            tool_from_model(
                FetchInput,
                web_fetch_handler,
                name="web.fetch",
                description="Fetch URL as markdown.",
            ),
            "Fetch URL",
            "Fetch URL and convert HTML to markdown-like text.",
        ),
        (
            tool_from_model(
                SearchInput,
                web_search_handler,
                name="web.search",
                description="Search web via Ollama API." if use_ollama_web_tools else "Build web search URL.",
            ),
            "Search web",
            (
                "Search web via Ollama web search API and return formatted results."
                if use_ollama_web_tools
                else "Return a DuckDuckGo search URL for the query."
            ),
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
