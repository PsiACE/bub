"""Republic-driven runtime battery used by runtime skill."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import Any

from republic import LLM, TapeEntry, Tool, ToolAutoResult
from republic.tape import InMemoryTapeStore, Tape

from bub.skills import discover_skills, load_skill_body

DEFAULT_MODEL = "openrouter:qwen/qwen3-coder-next"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
DEFAULT_MODEL_TIMEOUT_SECONDS = 90
DEFAULT_MAX_STEPS = 8
DEFAULT_MAX_TOKENS = 1024
CONTINUE_PROMPT = "Continue the task."
AGENTS_FILE_NAME = "AGENTS.md"
AGENT_PROFILE_FILE_NAME = "agent.yaml"
RUNTIME_ENABLED_ENV = "BUB_RUNTIME_ENABLED"
PRIMARY_API_KEY_ENV = "BUB_API_KEY"
RUNTIME_ENABLED_ON_VALUE = "1"
RUNTIME_ENABLED_OFF_VALUE = "0"
RUNTIME_ENABLED_AUTO_VALUE = "auto"
DEFAULT_SYSTEM_PROMPT = (
    "You are Bub runtime skill. Use tools for operations such as shell, file edits, "
    "skills lookup, and tape operations. Return concise natural language when done."
)


@dataclass(frozen=True)
class ParsedArgs:
    kwargs: dict[str, object]
    positional: list[str]


@dataclass(frozen=True)
class RuntimeSettings:
    model: str
    api_key: str | None
    api_base: str | None
    max_steps: int
    max_tokens: int
    timeout_seconds: int | None
    enabled: bool


@dataclass(frozen=True)
class RuntimeAgentProfile:
    system_prompt: str | None = None
    continue_prompt: str = CONTINUE_PROMPT


class RuntimeEngine:
    """Runtime engine with command compatibility and Republic model driving."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self._event_root = self.workspace / ".bub" / "runtime"
        self._event_root.mkdir(parents=True, exist_ok=True)
        self._settings = _load_runtime_settings()
        self._llm = _build_llm(self._settings)

    async def run(self, *, session_id: str, prompt: str) -> str | None:
        stripped = prompt.strip()
        if not stripped:
            return None
        if stripped.startswith(","):
            return await self._run_command(session_id=session_id, line=stripped)
        return await self._run_runtime(session_id=session_id, prompt=stripped)

    async def _run_runtime(self, *, session_id: str, prompt: str) -> str | None:
        if self._llm is None:
            return None

        tape = self._llm.tape(_session_tape_name(session_id))
        self._ensure_bootstrap_anchor(tape)
        tools = self._build_model_tools(session_id=session_id, tape=tape)
        next_prompt = prompt

        for step in range(1, self._settings.max_steps + 1):
            start = time.monotonic()
            try:
                output = await self._run_tools_once(tape=tape, prompt=next_prompt, tools=tools)
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                self._append_event(
                    session_id,
                    {
                        "type": "model",
                        "step": step,
                        "status": "error",
                        "elapsed_ms": elapsed_ms,
                        "error": f"{exc!s}",
                        "ts": datetime.now(UTC).isoformat(),
                    },
                )
                return None

            outcome = _resolve_tool_auto_result(output)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if outcome.kind == "text":
                self._append_event(
                    session_id,
                    {
                        "type": "model",
                        "step": step,
                        "status": "ok",
                        "elapsed_ms": elapsed_ms,
                        "ts": datetime.now(UTC).isoformat(),
                    },
                )
                return outcome.text
            if outcome.kind == "continue":
                self._append_event(
                    session_id,
                    {
                        "type": "model",
                        "step": step,
                        "status": "continue",
                        "elapsed_ms": elapsed_ms,
                        "ts": datetime.now(UTC).isoformat(),
                    },
                )
                next_prompt = CONTINUE_PROMPT
                continue
            self._append_event(
                session_id,
                {
                    "type": "model",
                    "step": step,
                    "status": "error",
                    "elapsed_ms": elapsed_ms,
                    "error": outcome.error,
                    "ts": datetime.now(UTC).isoformat(),
                },
            )
            return f"error: {outcome.error}"

        return f"error: max_steps_reached={self._settings.max_steps}"

    async def _run_tools_once(self, *, tape: Tape, prompt: str, tools: list[Tool]) -> ToolAutoResult:
        if self._settings.timeout_seconds is None:
            return await tape.run_tools_async(
                prompt=prompt,
                system_prompt=self._system_prompt(),
                max_tokens=self._settings.max_tokens,
                tools=tools,
                extra_headers={"HTTP-Referer": "https://bub.build/", "X-Title": "Bub"},
            )
        async with asyncio.timeout(self._settings.timeout_seconds):
            return await tape.run_tools_async(
                prompt=prompt,
                system_prompt=self._system_prompt(),
                max_tokens=self._settings.max_tokens,
                tools=tools,
                extra_headers={"HTTP-Referer": "https://bub.build/", "X-Title": "Bub"},
            )

    async def _run_command(self, *, session_id: str, line: str) -> str:
        tape = self._llm.tape(_session_tape_name(session_id)) if self._llm is not None else None
        if tape is not None:
            self._ensure_bootstrap_anchor(tape)
        raw_body = line[1:].strip()
        if not raw_body:
            return "error: empty command"

        name, args_tokens = _parse_internal_command(line)
        resolved_name = _resolve_internal_name(name)
        command_name = resolved_name if resolved_name in _internal_tool_names() else "bash"
        start = time.monotonic()
        try:
            if command_name == "bash":
                output = await self._run_shell(raw_body)
            else:
                output = await self._run_internal(
                    command_name=command_name,
                    args_tokens=args_tokens,
                    session_id=session_id,
                    tape=tape,
                )
            status = "ok"
        except Exception as exc:
            status = "error"
            output = f"{exc!s}"
        elapsed_ms = int((time.monotonic() - start) * 1000)

        event_payload = {
            "type": "command",
            "raw": line,
            "name": command_name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "output": output,
            "ts": datetime.now(UTC).isoformat(),
        }
        self._append_event(session_id, event_payload)
        if tape is not None:
            tape.append(TapeEntry.event("command", data=event_payload))
        if status == "error":
            return f"error: {output}"
        return output

    async def _run_internal(
        self,
        *,
        command_name: str,
        args_tokens: list[str],
        session_id: str,
        tape: Tape | None,
    ) -> str:
        args = _parse_kv_arguments(args_tokens)
        handler = self._internal_handlers().get(command_name)
        if handler is None:
            raise RuntimeError(f"unknown internal command: {command_name}")
        result = handler(args=args, session_id=session_id, tape=tape)
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    def _internal_handlers(self) -> dict[str, Any]:
        return {
            "help": self._command_help,
            "tools": self._command_tools,
            "tool.describe": self._command_tool_describe,
            "skills.list": self._command_skills_list,
            "skills.describe": self._command_skills_describe,
            "tape.info": self._command_tape_info,
            "tape.search": self._command_tape_search,
            "tape.handoff": self._command_tape_handoff,
            "tape.anchors": self._command_tape_anchors,
            "fs.read": self._command_fs_read,
            "fs.write": self._command_fs_write,
            "fs.edit": self._command_fs_edit,
            "quit": self._command_quit,
        }

    def _command_help(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args, session_id, tape
        return _help_text()

    def _command_tools(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args, session_id, tape
        return "\n".join(sorted(_internal_tool_names()))

    def _command_tool_describe(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = session_id, tape
        name = _arg_as_str(args, "name") or (args.positional[0] if args.positional else "")
        if not name:
            raise RuntimeError("missing tool name")
        return _tool_describe(name)

    def _command_skills_list(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args, session_id, tape
        skills = discover_skills(self.workspace)
        if not skills:
            return "(no skills)"
        return "\n".join(f"{skill.name} ({skill.source}): {skill.description}" for skill in skills)

    def _command_skills_describe(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = session_id, tape
        name = _arg_as_str(args, "name") or (args.positional[0] if args.positional else "")
        if not name:
            raise RuntimeError("missing skill name")
        body = load_skill_body(name, self.workspace)
        if body is None:
            raise RuntimeError(f"skill not found: {name}")
        return body

    def _command_tape_info(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args
        entries = self._read_entries(session_id=session_id, tape=tape)
        anchors = [entry for entry in entries if entry.get("kind") == "anchor"]
        last_anchor = str(anchors[-1].get("name") or "-") if anchors else "-"
        return f"name: {session_id}\nentries: {len(entries)}\nanchors: {len(anchors)}\nlast_anchor: {last_anchor}"

    def _command_tape_search(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        query = _arg_as_str(args, "query") or (args.positional[0] if args.positional else "")
        if not query:
            raise RuntimeError("missing query")
        limit = _arg_as_int(args, "limit", default=20) or 20
        lowered = query.casefold()
        matches: list[str] = []
        for entry in self._read_entries(session_id=session_id, tape=tape):
            serialized = json.dumps(entry, ensure_ascii=False)
            if lowered in serialized.casefold():
                matches.append(serialized)
                if len(matches) >= limit:
                    break
        if not matches:
            return "(no matches)"
        return "\n".join(matches)

    def _command_tape_handoff(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        name = _arg_as_str(args, "name") or (args.positional[0] if args.positional else "handoff")
        summary = _arg_as_str(args, "summary") or ""
        if tape is not None:
            state = {"summary": summary} if summary else None
            tape.handoff(name, state=state)
            return f"anchor added: {name}"
        self._append_event(
            session_id,
            {
                "type": "anchor",
                "name": name,
                "summary": summary,
                "ts": datetime.now(UTC).isoformat(),
            },
        )
        return f"anchor added: {name}"

    def _command_tape_anchors(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args
        anchors = [
            entry for entry in self._read_entries(session_id=session_id, tape=tape) if entry.get("kind") == "anchor"
        ]
        if not anchors:
            return "(no anchors)"
        return "\n".join(str(entry.get("name") or "-") for entry in anchors)

    def _command_fs_read(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = session_id, tape
        path = _arg_as_str(args, "path") or (args.positional[0] if args.positional else "")
        if not path:
            raise RuntimeError("missing path")
        offset = _arg_as_int(args, "offset", default=0) or 0
        limit = _arg_as_int(args, "limit")
        return self._fs_read(path, offset=offset, limit=limit)

    def _command_fs_write(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = session_id, tape
        path = _arg_as_str(args, "path") or (args.positional[0] if args.positional else "")
        content = _arg_as_str(args, "content")
        if not path or content is None:
            raise RuntimeError("missing path/content")
        return self._fs_write(path, content)

    def _command_fs_edit(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = session_id, tape
        path = _arg_as_str(args, "path") or (args.positional[0] if args.positional else "")
        old = _arg_as_str(args, "old")
        new = _arg_as_str(args, "new")
        replace_all = bool(args.kwargs.get("replace_all", False))
        if not path or old is None or new is None:
            raise RuntimeError("missing path/old/new")
        return self._fs_edit(path, old, new, replace_all=replace_all)

    def _command_quit(self, *, args: ParsedArgs, session_id: str, tape: Tape | None) -> str:
        _ = args, session_id, tape
        return "exit"

    async def _run_shell(
        self, command: str, *, cwd: str | None = None, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS
    ) -> str:
        completed = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=cwd or str(self.workspace),
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

    def _build_model_tools(self, *, session_id: str, tape: Tape) -> list[Tool]:  # noqa: C901
        async def bash(cmd: str, cwd: str | None = None, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> str:
            return await self._run_shell(cmd, cwd=cwd, timeout_seconds=timeout_seconds)

        def fs_read(path: str, offset: int = 0, limit: int | None = None) -> str:
            return self._fs_read(path, offset=offset, limit=limit)

        def fs_write(path: str, content: str) -> str:
            return self._fs_write(path, content)

        def fs_edit(path: str, old: str, new: str, replace_all: bool = False) -> str:
            return self._fs_edit(path, old, new, replace_all=replace_all)

        def skills_list() -> str:
            return self._command_skills_list(
                args=ParsedArgs(kwargs={}, positional=[]), session_id=session_id, tape=tape
            )

        def skills_describe(name: str) -> str:
            args = ParsedArgs(kwargs={"name": name}, positional=[])
            return self._command_skills_describe(args=args, session_id=session_id, tape=tape)

        def tape_info() -> str:
            return self._command_tape_info(args=ParsedArgs(kwargs={}, positional=[]), session_id=session_id, tape=tape)

        def tape_search(query: str, limit: int = 20) -> str:
            args = ParsedArgs(kwargs={"query": query, "limit": limit}, positional=[])
            return self._command_tape_search(args=args, session_id=session_id, tape=tape)

        def tape_handoff(name: str = "handoff", summary: str = "") -> str:
            args = ParsedArgs(kwargs={"name": name, "summary": summary}, positional=[])
            return self._command_tape_handoff(args=args, session_id=session_id, tape=tape)

        def tape_anchors() -> str:
            return self._command_tape_anchors(
                args=ParsedArgs(kwargs={}, positional=[]), session_id=session_id, tape=tape
            )

        tools = [
            ("bash", "Run shell command in workspace with timeout.", bash),
            ("fs.read", "Read a UTF-8 file with optional offset and limit.", fs_read),
            ("fs.write", "Write UTF-8 content to a file path.", fs_write),
            ("fs.edit", "Replace text once or all in a file.", fs_edit),
            ("skills.list", "List discovered skills with source and description.", skills_list),
            ("skills.describe", "Read SKILL.md body by skill name.", skills_describe),
            ("tape.info", "Show session tape summary.", tape_info),
            ("tape.search", "Search tape entries by query.", tape_search),
            ("tape.handoff", "Create one anchor event.", tape_handoff),
            ("tape.anchors", "List anchor names.", tape_anchors),
        ]
        return [Tool.from_callable(func, name=name, description=description) for name, description, func in tools]

    def _system_prompt(self) -> str:
        blocks = [DEFAULT_SYSTEM_PROMPT]
        if workspace_prompt := _read_workspace_agents_prompt(self.workspace):
            blocks.append(workspace_prompt)
        return "\n\n".join(blocks)

    def _read_entries(self, *, session_id: str, tape: Tape | None) -> list[dict[str, object]]:
        if tape is not None:
            entries: list[dict[str, object]] = []
            for entry in tape.read_entries():
                entries.append({
                    "id": entry.id,
                    "kind": entry.kind,
                    "name": entry.payload.get("name") if isinstance(entry.payload, dict) else None,
                    "payload": entry.payload,
                    "meta": entry.meta,
                })
            return entries
        return self._read_events_file(session_id)

    @staticmethod
    def _ensure_bootstrap_anchor(tape: Tape) -> None:
        for entry in tape.read_entries():
            if entry.kind == "anchor":
                return
        tape.handoff("session/start", state={"owner": "human"})

    def _fs_read(self, raw_path: str, *, offset: int = 0, limit: int | None = None) -> str:
        path = self._resolve_path(raw_path)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = max(0, min(offset, len(lines)))
        end = len(lines) if limit is None else min(len(lines), start + max(0, limit))
        return "\n".join(lines[start:end])

    def _fs_write(self, raw_path: str, content: str) -> str:
        path = self._resolve_path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"wrote: {path}"

    def _fs_edit(self, raw_path: str, old: str, new: str, *, replace_all: bool) -> str:
        path = self._resolve_path(raw_path)
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise RuntimeError("old text not found")
        if replace_all:
            count = text.count(old)
            path.write_text(text.replace(old, new), encoding="utf-8")
            return f"updated: {path} occurrences={count}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"updated: {path} occurrences=1"

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return (self.workspace / path).resolve()

    def _append_event(self, session_id: str, payload: dict[str, object]) -> None:
        file_path = self._event_file(session_id)
        with file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _read_events_file(self, session_id: str) -> list[dict[str, object]]:
        file_path = self._event_file(session_id)
        if not file_path.exists():
            return []
        events: list[dict[str, object]] = []
        for raw in file_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    def _event_file(self, session_id: str) -> Path:
        slug = md5(session_id.encode("utf-8")).hexdigest()[:16]  # noqa: S324
        return self._event_root / f"{slug}.jsonl"


@dataclass(frozen=True)
class _ToolAutoOutcome:
    kind: str
    text: str = ""
    error: str = ""


def _resolve_tool_auto_result(output: ToolAutoResult) -> _ToolAutoOutcome:
    if output.kind == "text":
        return _ToolAutoOutcome(kind="text", text=output.text or "")
    if output.kind == "tools" or output.tool_calls or output.tool_results:
        return _ToolAutoOutcome(kind="continue")
    if output.error is None:
        return _ToolAutoOutcome(kind="error", error="tool_auto_error: unknown")
    error_kind = getattr(output.error.kind, "value", str(output.error.kind))
    return _ToolAutoOutcome(kind="error", error=f"{error_kind}: {output.error.message}")


def _build_llm(settings: RuntimeSettings) -> LLM | None:
    if not settings.enabled:
        return None
    return LLM(
        settings.model,
        api_key=settings.api_key,
        api_base=settings.api_base,
        tape_store=InMemoryTapeStore(),
    )


def _load_runtime_settings() -> RuntimeSettings:
    model = _first_non_empty([os.getenv("BUB_MODEL"), DEFAULT_MODEL]) or DEFAULT_MODEL
    api_key = _resolve_runtime_api_key()
    api_base = _first_non_empty([os.getenv("BUB_API_BASE")])
    max_steps = _int_env("BUB_RUNTIME_MAX_STEPS", default=DEFAULT_MAX_STEPS)
    max_tokens = _int_env("BUB_RUNTIME_MAX_TOKENS", default=DEFAULT_MAX_TOKENS)
    timeout_seconds = _int_env("BUB_RUNTIME_MODEL_TIMEOUT_SECONDS", default=DEFAULT_MODEL_TIMEOUT_SECONDS)
    mode = _resolve_runtime_enabled_mode()
    enabled = _resolve_runtime_enabled(mode=mode, model=model, api_key=api_key)

    return RuntimeSettings(
        model=model,
        api_key=api_key,
        api_base=api_base,
        max_steps=max_steps,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )


def _model_requires_api_key(model: str) -> bool:
    prefixes = ("openrouter:", "openai:", "anthropic:", "gemini:", "xai:", "groq:", "mistral:", "deepseek:")
    lowered = model.casefold()
    return lowered.startswith(prefixes)


def _resolve_runtime_api_key() -> str | None:
    return _first_non_empty([os.getenv(PRIMARY_API_KEY_ENV)])


def _resolve_runtime_enabled(*, mode: str, model: str, api_key: str | None) -> bool:
    if mode == RUNTIME_ENABLED_ON_VALUE:
        return True
    if mode == RUNTIME_ENABLED_OFF_VALUE:
        return False
    requires_key = _model_requires_api_key(model)
    return bool(api_key) or not requires_key


def _resolve_runtime_enabled_mode() -> str:
    mode = _first_non_empty([os.getenv(RUNTIME_ENABLED_ENV), RUNTIME_ENABLED_AUTO_VALUE]) or RUNTIME_ENABLED_AUTO_VALUE
    lowered = mode.casefold()
    if lowered in {RUNTIME_ENABLED_ON_VALUE, RUNTIME_ENABLED_OFF_VALUE, RUNTIME_ENABLED_AUTO_VALUE}:
        return lowered
    return RUNTIME_ENABLED_AUTO_VALUE


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _int_env(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _read_workspace_agents_prompt(workspace: Path) -> str:
    prompt_path = workspace / AGENTS_FILE_NAME
    if not prompt_path.is_file():
        return ""
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _session_tape_name(session_id: str) -> str:
    slug = md5(session_id.encode("utf-8")).hexdigest()[:16]  # noqa: S324
    return f"runtime:{slug}"


def _parse_internal_command(line: str) -> tuple[str, list[str]]:
    body = line.strip()[1:].strip()
    words = _parse_command_words(body)
    if not words:
        return "", []
    return words[0], words[1:]


def _parse_command_words(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return []


def _parse_kv_arguments(tokens: list[str]) -> ParsedArgs:
    kwargs: dict[str, object] = {}
    positional: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                name, value = key.split("=", 1)
                kwargs[name] = value
                index += 1
                continue
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                kwargs[key] = tokens[index + 1]
                index += 2
                continue
            kwargs[key] = True
            index += 1
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            kwargs[key] = value
            index += 1
            continue
        positional.append(token)
        index += 1
    return ParsedArgs(kwargs=kwargs, positional=positional)


def _resolve_internal_name(name: str) -> str:
    aliases = {
        "tool": "tool.describe",
        "tape": "tape.info",
        "skill": "skills.describe",
    }
    return aliases.get(name, name)


def _internal_tool_names() -> set[str]:
    return {
        "bash",
        "help",
        "tools",
        "tool.describe",
        "skills.list",
        "skills.describe",
        "tape.info",
        "tape.search",
        "tape.handoff",
        "tape.anchors",
        "fs.read",
        "fs.write",
        "fs.edit",
        "quit",
    }


def _tool_describe(name: str) -> str:
    descriptions = {
        "bash": "Run shell command in workspace with timeout.",
        "help": "Show internal command usage.",
        "tools": "List available internal tools.",
        "tool.describe": "Show one tool description.",
        "skills.list": "List discovered skills with source and description.",
        "skills.describe": "Show one skill body by name.",
        "tape.info": "Show session tape summary.",
        "tape.search": "Search session tape entries by query.",
        "tape.handoff": "Create an anchor event.",
        "tape.anchors": "List anchor names.",
        "fs.read": "Read a UTF-8 file with optional offset and limit.",
        "fs.write": "Write UTF-8 file content.",
        "fs.edit": "Replace text in file once or all.",
        "quit": "Return exit marker.",
    }
    description = descriptions.get(name)
    if description is None:
        raise RuntimeError(f"unknown tool: {name}")
    return f"{name}: {description}"


def _help_text() -> str:
    return (
        "Commands use ',' at line start.\n"
        "Known internal commands:\n"
        "  ,help\n"
        "  ,tools\n"
        "  ,tool.describe name=fs.read\n"
        "  ,skills.list\n"
        "  ,skills.describe name=friendly-python\n"
        "  ,tape.info\n"
        "  ,tape.search query=error\n"
        "  ,tape.handoff name=phase-1 summary='done'\n"
        "  ,tape.anchors\n"
        "  ,fs.read path=README.md\n"
        "  ,fs.write path=tmp.txt content='hello'\n"
        "  ,fs.edit path=tmp.txt old=hello new=world\n"
        "  ,quit\n"
        "Any unknown command after ',' is executed as shell via bash."
    )


def _arg_as_str(args: ParsedArgs, key: str) -> str | None:
    value = args.kwargs.get(key)
    if value is None:
        return None
    return str(value)


def _arg_as_int(args: ParsedArgs, key: str, default: int | None = None) -> int | None:
    value = args.kwargs.get(key)
    if value is None:
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
