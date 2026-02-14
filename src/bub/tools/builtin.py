"""Built-in tool definitions."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import parse as urllib_parse

import html2markdown
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field
from republic import ToolContext

from bub.tape.service import TapeService
from bub.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from bub.app.runtime import AppRuntime

DEFAULT_OLLAMA_WEB_API_BASE = "https://ollama.com/api"
WEB_REQUEST_TIMEOUT_SECONDS = 20
SUBPROCESS_TIMEOUT_SECONDS = 30
MAX_FETCH_BYTES = 1_000_000
WEB_USER_AGENT = "bub-web-tools/1.0"
SESSION_ID_ENV_VAR = "BUB_SESSION_ID"


class BashInput(BaseModel):
    cmd: str = Field(..., description="Shell command")
    cwd: str | None = Field(default=None, description="Working directory")
    timeout_seconds: int = Field(
        default=SUBPROCESS_TIMEOUT_SECONDS, ge=1, description="Maximum seconds to allow command to run"
    )


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
    all_tapes: bool = Field(default=False, description="Search all tapes instead of current tape")


class TapeResetInput(BaseModel):
    archive: bool = Field(default=False)


class SkillNameInput(BaseModel):
    name: str = Field(..., description="Skill name")


class EmptyInput(BaseModel):
    pass


class ScheduleAddInput(BaseModel):
    after_seconds: int | None = Field(None, description="If set, schedule to run after this many seconds from now")
    interval_seconds: int | None = Field(None, description="If set, repeat at this interval")
    cron: str | None = Field(
        None, description="If set, run with cron expression in crontab format: minute hour day month day_of_week"
    )
    message: str = Field(..., description="Reminder message to send")


class ScheduleRemoveInput(BaseModel):
    job_id: str = Field(..., description="Job id to remove")


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
    runtime: AppRuntime,
    session_id: str,
) -> None:
    """Register built-in tools and internal commands."""
    from bub.tools.schedule import run_scheduled_reminder

    register = registry.register

    @register(name="bash", short_description="Run shell command", model=BashInput)
    async def run_bash(params: BashInput) -> str:
        """Execute bash in workspace. Non-zero exit raises an error.
        IMPORTANT: please DO NOT use sleep to delay execution, use schedule.add tool instead.
        """
        cwd = params.cwd or str(workspace)
        executable = shutil.which("bash") or "bash"
        env = dict(os.environ)
        env[SESSION_ID_ENV_VAR] = session_id
        completed = await asyncio.create_subprocess_exec(
            executable,
            "-lc",
            params.cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        async with asyncio.timeout(params.timeout_seconds):
            stdout_bytes, stderr_bytes = await completed.communicate()
        stdout_text = (stdout_bytes or b"").decode("utf-8").strip()
        stderr_text = (stderr_bytes or b"").decode("utf-8").strip()
        if completed.returncode != 0:
            message = stderr_text or stdout_text or f"exit={completed.returncode}"
            raise RuntimeError(f"exit={completed.returncode}: {message}")
        return stdout_text or "(no output)"

    @register(name="fs.read", short_description="Read file content", model=ReadInput)
    def fs_read(params: ReadInput) -> str:
        """Read UTF-8 text with optional offset and limit."""
        file_path = _resolve_path(workspace, params.path)
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = min(params.offset, len(lines))
        end = len(lines) if params.limit is None else min(len(lines), start + params.limit)
        return "\n".join(lines[start:end])

    @register(name="fs.write", short_description="Write file content", model=WriteInput)
    def fs_write(params: WriteInput) -> str:
        """Write UTF-8 text to path, creating parent directory if needed."""
        file_path = _resolve_path(workspace, params.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(params.content, encoding="utf-8")
        return f"wrote: {file_path}"

    @register(name="fs.edit", short_description="Edit file content", model=EditInput)
    def fs_edit(params: EditInput) -> str:
        """Replace one or all occurrences of old text in file."""
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

    async def _fetch_markdown_from_url(raw_url: str) -> str:
        import aiohttp

        url = _normalize_url(raw_url)
        if not url:
            return "error: invalid url"

        try:
            async with (
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=WEB_REQUEST_TIMEOUT_SECONDS)) as session,
                session.get(url, headers={"User-Agent": WEB_USER_AGENT}) as response,
            ):
                content_bytes = await response.content.read(MAX_FETCH_BYTES + 1)
                truncated = len(content_bytes) > MAX_FETCH_BYTES
                content = content_bytes[:MAX_FETCH_BYTES].decode("utf-8", errors="replace")
        except aiohttp.ClientError as exc:
            return f"HTTP error: {exc!s}"
        rendered = _html_to_markdown(content).strip()
        if not rendered:
            return "error: empty response body"
        if truncated:
            return f"{rendered}\n\n[truncated: response exceeded byte limit]"
        return rendered

    @register(name="web.fetch", short_description="Fetch URL as markdown", model=FetchInput)
    async def web_fetch_default(params: FetchInput) -> str:
        """Fetch URL and convert HTML to markdown-like text."""
        return await _fetch_markdown_from_url(params.url)

    @register(name="schedule.add", short_description="Add a cron schedule", model=ScheduleAddInput, context=True)
    def schedule_add(params: ScheduleAddInput, context: ToolContext) -> str:
        """Schedule a reminder message to be sent to current session in the future. You can specify either of the following scheduling options:
        - after_seconds: run once after this many seconds from now
        - interval_seconds: run repeatedly at this interval
        - cron: run with cron expression in crontab format: minute hour day month day_of_week
        """
        job_id = str(uuid.uuid4())[:8]
        if params.after_seconds is not None:
            trigger = DateTrigger(run_date=datetime.now(UTC) + timedelta(seconds=params.after_seconds))
        elif params.interval_seconds is not None:
            trigger = IntervalTrigger(seconds=params.interval_seconds)
        else:
            try:
                trigger = CronTrigger.from_crontab(params.cron)
            except ValueError as exc:
                raise RuntimeError(f"invalid cron expression: {params.cron}") from exc

        try:
            job = runtime.scheduler.add_job(
                run_scheduled_reminder,
                trigger=trigger,
                id=job_id,
                kwargs={"message": params.message, "session_id": session_id, "workspace": str(runtime.workspace)},
                coalesce=True,
                max_instances=1,
            )
        except ConflictingIdError as exc:
            raise RuntimeError(f"job id already exists: {job_id}") from exc

        next_run = "-"
        if isinstance(job.next_run_time, datetime):
            next_run = job.next_run_time.isoformat()
        return f"scheduled: {job.id} next={next_run}"

    @register(name="schedule.remove", short_description="Remove a scheduled job", model=ScheduleRemoveInput)
    def schedule_remove(params: ScheduleRemoveInput) -> str:
        """Remove one scheduled job by id."""
        try:
            runtime.scheduler.remove_job(params.job_id)
        except JobLookupError as exc:
            raise RuntimeError(f"job not found: {params.job_id}") from exc
        return f"removed: {params.job_id}"

    @register(name="schedule.list", short_description="List scheduled jobs", model=EmptyInput)
    def schedule_list(_params: EmptyInput) -> str:
        """List scheduled jobs for current workspace."""
        jobs = runtime.scheduler.get_jobs()
        rows: list[str] = []
        for job in jobs:
            next_run = "-"
            if isinstance(job.next_run_time, datetime):
                next_run = job.next_run_time.isoformat()
            message = str(job.kwargs.get("message", ""))
            job_session = job.kwargs.get("session_id")
            if job_session and job_session != session_id:
                continue
            rows.append(f"{job.id} next={next_run} msg={message}")

        if not rows:
            return "(no scheduled jobs)"

        return "\n".join(rows)

    if runtime.settings.ollama_api_key:

        @register(name="web.search", short_description="Search the web", model=SearchInput)
        async def web_search_ollama(params: SearchInput) -> str:
            import aiohttp

            api_key = runtime.settings.ollama_api_key
            if not api_key:
                return "error: ollama api key is not configured"

            api_base = _normalize_api_base(runtime.settings.ollama_api_base or DEFAULT_OLLAMA_WEB_API_BASE)
            if not api_base:
                return "error: invalid ollama api base url"

            endpoint = f"{api_base}/web_search"
            payload = {
                "query": params.query,
                "max_results": params.max_results,
            }
            try:
                async with (
                    aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=WEB_REQUEST_TIMEOUT_SECONDS)) as session,
                    session.post(
                        endpoint,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": WEB_USER_AGENT,
                        },
                    ) as response,
                ):
                    response_body = await response.text()
            except aiohttp.ClientError as exc:
                return f"HTTP error: {exc!s}"

            try:
                data = json.loads(response_body)
            except json.JSONDecodeError as exc:
                return f"error: invalid json response: {exc!s}"

            results = data.get("results")
            if not isinstance(results, list) or not results:
                return "none"
            return _format_search_results(results)

    else:

        @register(name="web.search", short_description="Search the web", model=SearchInput)
        def web_search_default(params: SearchInput) -> str:
            """Return a DuckDuckGo search URL for the query."""
            query = urllib_parse.quote_plus(params.query)
            return f"https://duckduckgo.com/?q={query}"

    @register(name="help", short_description="Show command help", model=EmptyInput)
    def command_help(_params: EmptyInput) -> str:
        """Show Bub internal command usage and examples."""
        return (
            "Commands use ',' at line start.\n"
            "Known names map to internal tools; other commands run through bash.\n"
            "Examples:\n"
            "  ,help\n"
            "  ,git status\n"
            "  , ls -la\n"
            "  ,tools\n"
            "  ,tool.describe name=fs.read\n"
            "  ,tape.handoff name=phase-1 summary='Bootstrap complete'\n"
            "  ,tape.anchors\n"
            "  ,tape.info\n"
            "  ,tape.search query=error\n"
            "  ,schedule.add cron='*/5 * * * *' message='echo hello'\n"
            "  ,schedule.list\n"
            "  ,schedule.remove job_id=my-job\n"
            "  ,skills.list\n"
            "  ,skills.describe name=friendly-python\n"
            "  ,quit\n"
        )

    @register(name="tools", short_description="List available tools", model=EmptyInput)
    def list_tools(_params: EmptyInput) -> str:
        """List all tools in compact mode."""
        return "\n".join(registry.compact_rows())

    @register(name="tool.describe", short_description="Show tool detail", model=ToolNameInput)
    def tool_describe(params: ToolNameInput) -> str:
        """Expand one tool description and schema."""
        return registry.detail(params.name)

    @register(name="tape.handoff", short_description="Create anchor handoff", model=HandoffInput)
    def handoff(params: HandoffInput) -> str:
        """Create tape anchor with optional summary and next_steps state."""
        anchor_name = params.name or "handoff"
        state: dict[str, object] = {}
        if params.summary:
            state["summary"] = params.summary
        if params.next_steps:
            state["next_steps"] = params.next_steps
        tape.handoff(anchor_name, state=state or None)
        return f"handoff created: {anchor_name}"

    @register(name="tape.anchors", short_description="List tape anchors", model=EmptyInput)
    def anchors(_params: EmptyInput) -> str:
        """List recent tape anchors."""
        rows = []
        for anchor in tape.anchors(limit=50):
            rows.append(f"{anchor.name} state={json.dumps(anchor.state, ensure_ascii=False)}")
        return "\n".join(rows) if rows else "(no anchors)"

    @register(name="tape.info", short_description="Show tape summary", model=EmptyInput)
    def tape_info(_params: EmptyInput) -> str:
        """Show tape summary with entry and anchor counts. It includes the following fields:
        - tape: tape name
        - entries: total number of entries
        - anchors: total number of anchors
        - last_anchor: name of last anchor or '-'
        - entries_since_last_anchor: number of entries since last anchor
        - approximate_context_length: approximate total length of message contents
        """
        info = tape.info()
        messages = tape.tape.read_messages()
        approximate_context_length = sum(len(msg.get("content", "")) for msg in messages)
        return "\n".join((
            f"tape={info.name}",
            f"entries={info.entries}",
            f"anchors={info.anchors}",
            f"last_anchor={info.last_anchor or '-'}",
            f"entries_since_last_anchor={info.entries_since_last_anchor}",
            f"approximate_context_length={approximate_context_length}",
        ))

    @register(name="tape.search", short_description="Search tape entries", model=TapeSearchInput)
    def tape_search(params: TapeSearchInput) -> str:
        """Search entries in tape by query. In reverse order."""
        entries = tape.search(params.query, limit=params.limit, all_tapes=params.all_tapes)
        if not entries:
            return "(no matches)"
        return "\n".join(f"#{entry.id} {entry.kind} {entry.payload}" for entry in entries)

    @register(name="tape.reset", short_description="Reset tape", model=TapeResetInput)
    def tape_reset(params: TapeResetInput) -> str:
        """Reset current tape; can archive before clearing."""
        result = tape.reset(archive=params.archive)
        runtime.reset_session_context(session_id)
        return result

    @register(name="skills.list", short_description="List skills", model=EmptyInput)
    def list_skills(_params: EmptyInput) -> str:
        """List all discovered skills in compact form."""
        skills = runtime.discover_skills()
        if not skills:
            return "(no skills)"
        return "\n".join(f"{skill.name}: {skill.description}" for skill in skills)

    @register(name="skills.describe", short_description="Load skill body", model=SkillNameInput)
    def describe_skill(params: SkillNameInput) -> str:
        """Load full SKILL.md body for one skill name."""
        body = runtime.load_skill_body(params.name)
        if not body:
            raise RuntimeError(f"skill not found: {params.name}")
        return body

    @register(name="quit", short_description="Exit program", model=EmptyInput)
    def quit_command(_params: EmptyInput) -> str:
        """Request exit from interactive CLI."""
        return "exit"
