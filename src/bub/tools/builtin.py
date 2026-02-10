"""Built-in tool definitions."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib.request import Request, urlopen

import html2markdown
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from pydantic import BaseModel, Field
from republic import ToolContext

from bub.tape.service import TapeService
from bub.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from bub.app.runtime import AppRuntime

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


class MemorySaveInput(BaseModel):
    content: str = Field(
        ...,
        description="The exact text the user asked you to remember — pass their words VERBATIM, "
        "do NOT paraphrase, summarize, or rewrite. This is APPENDED to existing long-term memory.",
    )


class MemoryDailyInput(BaseModel):
    content: str = Field(..., description="Content for today's notes")
    date: dt_date | None = Field(default=None, description="Date (YYYY-MM-DD), defaults to today")


class MemoryRecallInput(BaseModel):
    query: str | None = Field(default=None, description="Optional search query to filter memories")
    days: int = Field(default=7, ge=1, description="Days to look back for daily notes")


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


def _preview_single_line(text: str, *, limit: int = 100) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) > limit:
        return normalized[:limit] + "..."
    return normalized


def register_builtin_tools(
    registry: ToolRegistry,
    *,
    workspace: Path,
    tape: TapeService,
    runtime: AppRuntime,
    session_id: str,
) -> None:
    """Register built-in tools and internal commands."""

    register = registry.register
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    support_scheduling = runtime.scheduler.running

    @register(name="bash", short_description="Run shell command", model=BashInput)
    def run_bash(params: BashInput) -> str:
        """Execute bash in workspace. Non-zero exit raises an error."""
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

    @register(name="fs.glob", short_description="Glob files", model=GlobInput)
    def fs_glob(params: GlobInput) -> str:
        """Glob files under a base path."""
        base = _resolve_path(workspace, params.path)
        matches = sorted(base.glob(params.pattern))
        return "\n".join(str(path) for path in matches) or "(no matches)"

    @register(name="fs.grep", short_description="Grep files", model=GrepInput)
    def fs_grep(params: GrepInput) -> str:
        """Scan files recursively and return matching lines."""
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

    @register(name="web.fetch", short_description="Fetch URL as markdown", model=FetchInput)
    def web_fetch_default(params: FetchInput) -> str:
        """Fetch URL and convert HTML to markdown-like text."""
        return _fetch_markdown_from_url(params.url)

    def _run_scheduled_reminder(message: str) -> None:
        from bub.channels.events import InboundMessage

        bus = runtime.bus
        if bus is None:
            logger.error("cannot send scheduled reminder: bus is not set")
            return
        channel, chat_id = session_id.split(":", 1)
        inbound_message = InboundMessage(
            channel=channel,
            sender_id="scheduler",
            chat_id=chat_id,
            content=message,
        )
        logger.info("sending scheduled reminder to channel={} chat_id={} message={}", channel, chat_id, message)

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(bus.publish_inbound(inbound_message)))
            return

        asyncio.run(bus.publish_inbound(inbound_message))

    if support_scheduling:

        @register(name="schedule.add", short_description="Add a cron schedule", model=ScheduleAddInput, context=True)
        def schedule_add(params: ScheduleAddInput, context: ToolContext) -> str:
            """Create or replace a cron-based scheduled shell command."""
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
                    _run_scheduled_reminder,
                    trigger=trigger,
                    id=job_id,
                    kwargs={"message": params.message},
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
            if not jobs:
                return "(no scheduled jobs)"

            rows: list[str] = []
            for job in jobs:
                next_run = "-"
                if isinstance(job.next_run_time, datetime):
                    next_run = job.next_run_time.isoformat()
                message = str(job.kwargs.get("message", ""))
                rows.append(f"{job.id} next={next_run} msg={message}")
            return "\n".join(rows)

    if runtime.settings.ollama_api_key:

        @register(name="web.search", short_description="Search the web", model=SearchInput)
        def web_search_ollama(params: SearchInput) -> str:
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
            "  ,memory                              (show memory summary)\n"
            "  ,memory.save content='User prefers dark mode'\n"
            "  ,memory.daily content='Fixed tape reset bug'\n"
            "  ,memory.recall days=7\n"
            "  ,memory.clear\n"
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
        """Show tape summary with entry and anchor counts."""
        info = tape.info()
        return f"tape={info.name} entries={info.entries} anchors={info.anchors} last_anchor={info.last_anchor or '-'}"

    @register(name="tape.search", short_description="Search tape entries", model=TapeSearchInput)
    def tape_search(params: TapeSearchInput) -> str:
        """Search entries in tape by query."""
        entries = tape.search(params.query, limit=params.limit)
        if not entries:
            return "(no matches)"
        return "\n".join(f"#{entry.id} {entry.kind} {entry.payload}" for entry in entries)

    @register(name="tape.reset", short_description="Reset tape", model=TapeResetInput)
    def tape_reset(params: TapeResetInput) -> str:
        """Reset current tape; can archive before clearing."""
        return tape.reset(archive=params.archive)

    @register(name="skills.list", short_description="List skills", model=EmptyInput)
    def list_skills(_params: EmptyInput) -> str:
        """List all discovered skills in compact form."""
        if not runtime.skills:
            return "(no skills)"
        return "\n".join(f"{skill.name}: {skill.description}" for skill in runtime.skills)

    @register(name="skills.describe", short_description="Load skill body", model=SkillNameInput)
    def describe_skill(params: SkillNameInput) -> str:
        """Load full SKILL.md body for one skill name."""
        body = runtime.load_skill_body(params.name)
        if not body:
            raise RuntimeError(f"skill not found: {params.name}")
        return body

    @register(name="memory.save", short_description="Save to long-term memory", model=MemorySaveInput)
    def memory_save(params: MemorySaveInput) -> str:
        """Append to long-term memory. Content is stored verbatim."""
        tape.memory.save_long_term(params.content)
        return "appended to long-term memory"

    @register(name="memory.daily", short_description="Append to daily notes", model=MemoryDailyInput)
    def memory_daily(params: MemoryDailyInput) -> str:
        """Append content to today's (or specified date's) daily notes."""
        date_value = params.date.isoformat() if params.date is not None else None
        tape.memory.append_daily(params.content, date=date_value)
        return f"appended to daily notes ({date_value or 'today'})"

    @register(name="memory.recall", short_description="Recall memories", model=MemoryRecallInput)
    def memory_recall(params: MemoryRecallInput) -> str:
        """Recall long-term memory and recent daily notes."""
        snap = tape.memory.read()
        parts: list[str] = []
        if snap.long_term:
            parts.append(f"## Long-term Memory\n{snap.long_term}")
        dailies = snap.recent_dailies(days=params.days)
        if dailies:
            lines = ["## Recent Daily Notes"]
            for daily in dailies:
                lines.append(f"### {daily.date}")
                lines.append(daily.content)
            parts.append("\n".join(lines))
        if not parts:
            return "(no memories stored)"
        result = "\n\n".join(parts)
        if params.query:
            filtered = [line for line in result.splitlines() if params.query.lower() in line.lower()]
            if filtered:
                return "\n".join(filtered)
            return f"(no matches for '{params.query}')\n\nFull memory:\n{result}"
        return result

    @register(name="memory.show", short_description="Show memory summary", model=EmptyInput)
    def memory_show(_params: EmptyInput) -> str:
        """Show current memory zone summary."""
        snap = tape.memory.read()
        long_term_preview = _preview_single_line(snap.long_term, limit=100)
        return (
            f"version={snap.version}\n"
            f"long_term={'yes' if snap.long_term else 'no'}"
            + (f" ({long_term_preview})" if snap.long_term else "")
            + f"\ndaily_notes={len(snap.dailies)}"
            + (f" (latest: {snap.dailies[0].date})" if snap.dailies else "")
        )

    @register(name="memory.clear", short_description="Clear all memory", model=EmptyInput)
    def memory_clear(_params: EmptyInput) -> str:
        """Clear all memory (long-term and daily notes)."""
        tape.memory.clear()
        return "memory cleared"

    @register(name="quit", short_description="Exit program", model=EmptyInput)
    def quit_command(_params: EmptyInput) -> str:
        """Request exit from interactive CLI."""
        return "exit"
