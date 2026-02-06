"""Command parsing and formatting helpers for runtime session routing."""

from __future__ import annotations

import io
import re
import shlex
import shutil
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import cast

COMMAND_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-/:~]+$")
DOLLAR_SIGN = "$"
OPTION_TERMINATOR = "--"
RAW_TOOL_ARG_NAMES = {"bash", "bub"}
BASH_CWD_OPTION = "--cwd"
BASH_CMD_OPTION = "--cmd"
MIN_TOKENS_FOR_SPLIT_COMMAND = 2


@dataclass(frozen=True)
class TextSegment:
    text: str


@dataclass(frozen=True)
class ActionSegment:
    name: str
    kind: str  # "tool" | "shell"
    args: list[str]
    raw: str


Segment = TextSegment | ActionSegment


@dataclass(frozen=True)
class ActionOutcome:
    name: str
    status: str
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    intent: str
    origin: str


@dataclass(frozen=True)
class RouteResult:
    agent_input: str
    enter_agent: bool
    exit_requested: bool
    done_requested: bool


@dataclass(frozen=True)
class AssistantResult:
    followup_input: str
    exit_requested: bool
    done_requested: bool
    visible_text: str


def parse_segments(raw: str, tool_names: set[str]) -> list[Segment]:
    segments: list[Segment] = []
    pos = 0
    while pos < len(raw):
        cmd_start = _find_command_start(raw, pos)
        if cmd_start < 0:
            if pos < len(raw):
                segments.append(TextSegment(raw[pos:]))
            break
        if cmd_start > pos:
            segments.append(TextSegment(raw[pos:cmd_start]))
        parsed = _parse_command_at(raw, cmd_start, tool_names)
        if parsed is None:
            segments.append(TextSegment(raw[cmd_start : cmd_start + 1]))
            pos = cmd_start + 1
            continue
        segment, end = parsed
        segments.append(segment)
        pos = end
    return segments


def format_action_block(outcome: ActionOutcome) -> str:
    intent = outcome.intent.strip()
    if outcome.status == "ok":
        content = outcome.stdout.strip() or "(no output)"
        return f'<cmd name="{outcome.name}" status="ok">\n{content}\n</cmd>'
    error = outcome.stderr.strip() or "command failed"
    return f'<cmd name="{outcome.name}" status="error">\nerror: {error}\nintent: {intent}\n</cmd>'


def format_shell_args(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def build_tool_kwargs(segment: ActionSegment) -> dict:
    if segment.name == "bash":
        return _bash_tool_kwargs(segment.args)
    if segment.name == "bub":
        return {"args": list(segment.args)}
    return _generic_tool_kwargs(segment.args)


def normalize_command_output(output: object) -> tuple[bool, str]:
    text = str(output or "").strip()
    if text.startswith("error:"):
        return False, text.removeprefix("error:").strip() or "command failed"
    return True, text


def is_quit_outcome(outcome: ActionOutcome) -> bool:
    return outcome.name == "quit" and outcome.status == "ok" and outcome.stdout.strip() == "exit"


def is_debug_outcome(outcome: ActionOutcome) -> bool:
    return outcome.name == "debug" and outcome.status == "ok" and outcome.stdout.strip() == "toggle"


def is_done_outcome(outcome: ActionOutcome) -> bool:
    return outcome.name == "done" and outcome.status == "ok" and outcome.stdout.strip() == "done"


def strip_leading_dollar(raw: str) -> str | None:
    stripped = raw.lstrip()
    if not stripped.startswith(DOLLAR_SIGN):
        return None
    idx = raw.find(DOLLAR_SIGN)
    remainder = raw[idx + 1 :]
    if not remainder:
        return ""
    check = remainder.lstrip()
    if not check:
        return ""
    return check


def segments_are_only_text(segments: Sequence[object]) -> bool:
    return all(isinstance(segment, TextSegment) for segment in segments)


def _find_command_start(raw: str, start: int) -> int:
    in_single = False
    in_double = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if escape:
            escape = False
            continue
        if ch == "\\" and not in_single:
            escape = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if ch == DOLLAR_SIGN and not in_single and not in_double and (idx == 0 or raw[idx - 1].isspace()):
            return idx
    return -1


def _parse_command_at(
    raw: str,
    start: int,
    tool_names: set[str],
) -> tuple[ActionSegment, int] | None:
    tokens = list(_tokenize(raw[start:]))
    if not tokens:
        return None

    parsed_command = _consume_command_token(tokens)
    if parsed_command is None:
        return None
    cmd_name, token_idx, command_end_pos = parsed_command

    if not _is_command_name(cmd_name):
        return None

    kind = _command_kind(cmd_name, tool_names)
    if kind is None:
        return None

    allow_raw_tool_tail = _is_command_at_line_start(raw, start)
    arg_tokens = _collect_arg_tokens(
        tokens,
        token_idx,
        kind=kind,
        cmd_name=cmd_name,
        allow_raw_tool_tail=allow_raw_tool_tail,
    )
    args = [tok for tok, _ in arg_tokens]
    end_pos = command_end_pos if not arg_tokens else arg_tokens[-1][1]

    segment = ActionSegment(
        name=cmd_name,
        kind=kind,
        args=args,
        raw=raw[start : start + end_pos],
    )
    return segment, start + end_pos


def _tokenize(text: str) -> Iterator[tuple[str, int]]:
    lex = shlex.shlex(io.StringIO(text), posix=True)
    lex.wordchars += "$=.-/:"
    lex.whitespace_split = True
    lex.commenters = ""
    while True:
        token = lex.get_token()
        if token in (None, ""):
            break
        if not isinstance(token, str):
            continue
        end_pos = cast(int, lex.instream.tell())  # type: ignore[attr-defined]
        yield token, end_pos


def _command_kind(name: str, tool_names: set[str]) -> str | None:
    if name in tool_names:
        return "tool"
    if _shell_command_exists(name):
        return "shell"
    return None


def _shell_command_exists(name: str) -> bool:
    if _is_path_like(name):
        return True
    return shutil.which(name) is not None


def _is_command_name(name: str) -> bool:
    if not name:
        return False
    if not name.isascii():
        return False
    if not any(ch.isalpha() or ch == "_" for ch in name):
        return False
    return COMMAND_NAME_RE.match(name) is not None


def _is_path_like(token: str) -> bool:
    return token.startswith(("./", "../", "/", "~/")) or "/" in token


def _bash_tool_kwargs(args: list[str]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    cmd_parts: list[str] = []
    idx = 0
    while idx < len(args):
        next_idx = _consume_bash_special_arg(args, idx, kwargs)
        if next_idx is not None:
            idx = next_idx
            continue
        cmd_parts.append(args[idx])
        idx += 1
    cmd = " ".join(cmd_parts).strip()
    if "cmd" in kwargs and cmd:
        kwargs["cmd"] = f"{kwargs['cmd']} {cmd}".strip()
    else:
        kwargs.setdefault("cmd", cmd)
    return kwargs


def _generic_tool_kwargs(args: list[str]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token.startswith("--"):
            idx = _consume_long_option(args, idx, kwargs)
            continue
        if "=" in token:
            name, value = token.split("=", 1)
            kwargs[name] = value
            idx += 1
            continue
        arg_list = cast(list[str], kwargs.setdefault("args", []))
        arg_list.append(token)
        idx += 1
    return kwargs


def _consume_long_option(
    args: list[str],
    idx: int,
    kwargs: dict[str, object],
) -> int:
    option = args[idx][2:]
    if "=" in option:
        name, value = option.split("=", 1)
        kwargs[name] = value
        return idx + 1
    if idx + 1 < len(args) and not args[idx + 1].startswith("--"):
        kwargs[option] = args[idx + 1]
        return idx + 2
    kwargs[option] = True
    return idx + 1


def _consume_bash_special_arg(
    args: list[str],
    idx: int,
    kwargs: dict[str, object],
) -> int | None:
    token = args[idx]
    key: str | None = None
    value: str | None = None
    next_idx: int | None = None

    if token.startswith("cwd=") or token.startswith(f"{BASH_CWD_OPTION}="):
        key, value, next_idx = "cwd", token.split("=", 1)[1], idx + 1
    elif token == BASH_CWD_OPTION and idx + 1 < len(args):
        key, value, next_idx = "cwd", args[idx + 1], idx + 2
    elif token.startswith("cmd=") or token.startswith(f"{BASH_CMD_OPTION}="):
        key, value, next_idx = "cmd", token.split("=", 1)[1], idx + 1
    elif token == BASH_CMD_OPTION and idx + 1 < len(args):
        key, value, next_idx = "cmd", args[idx + 1], idx + 2

    if key is None or value is None or next_idx is None:
        return None
    kwargs[key] = value
    return next_idx


def _consume_command_token(tokens: list[tuple[str, int]]) -> tuple[str, int, int] | None:
    first_token, first_end = tokens[0]
    if first_token == DOLLAR_SIGN:
        if len(tokens) < MIN_TOKENS_FOR_SPLIT_COMMAND:
            return None
        cmd_token, cmd_end = tokens[1]
        return cmd_token, 2, cmd_end
    if first_token.startswith(DOLLAR_SIGN):
        cmd_name = first_token[1:]
        if not cmd_name:
            return None
        return cmd_name, 1, first_end
    return None


def _collect_arg_tokens(
    tokens: list[tuple[str, int]],
    start_idx: int,
    *,
    kind: str,
    cmd_name: str,
    allow_raw_tool_tail: bool,
) -> list[tuple[str, int]]:
    arg_tokens: list[tuple[str, int]] = []
    pending_value = False
    idx = start_idx
    while idx < len(tokens):
        token, token_end = tokens[idx]
        if _looks_like_command_start(token):
            break
        if token == OPTION_TERMINATOR and cmd_name not in RAW_TOOL_ARG_NAMES:
            break
        if kind == "shell":
            arg_tokens.append((token, token_end))
            idx += 1
            continue
        accepted, pending_value = _consume_tool_arg_token(
            token,
            token_end,
            pending_value=pending_value,
            cmd_name=cmd_name,
            allow_raw_tool_tail=allow_raw_tool_tail,
            arg_tokens=arg_tokens,
        )
        if not accepted:
            break
        idx += 1
    return arg_tokens


def _consume_tool_arg_token(
    token: str,
    token_end: int,
    *,
    pending_value: bool,
    cmd_name: str,
    allow_raw_tool_tail: bool,
    arg_tokens: list[tuple[str, int]],
) -> tuple[bool, bool]:
    if cmd_name in RAW_TOOL_ARG_NAMES and allow_raw_tool_tail:
        arg_tokens.append((token, token_end))
        return True, False
    if pending_value:
        arg_tokens.append((token, token_end))
        return True, False
    if token.startswith("--"):
        arg_tokens.append((token, token_end))
        return True, "=" not in token
    if "=" in token:
        arg_tokens.append((token, token_end))
        return True, False
    return False, False


def _looks_like_command_start(token: str) -> bool:
    return token == DOLLAR_SIGN or token.startswith(DOLLAR_SIGN)


def _is_command_at_line_start(raw: str, start: int) -> bool:
    line_start = raw.rfind("\n", 0, start) + 1
    return not raw[line_start:start].strip()
