"""Slash command adapters for /bub and !bub prefixes."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from datetime import UTC, datetime

from bub.core.commands import parse_command_words, parse_kv_arguments

AUTO_HANDOFF_NAME_PREFIX = "handoff/auto"
AUTO_NEW_SESSION_PREFIX = "session"


@dataclass(frozen=True)
class BubCommandResult:
    """Result of parsing a prefixed Bub command."""

    prompt: str
    session_name: str | None = None


def parse_bub_command(content: str, *, prefix: str) -> BubCommandResult | None:
    """Parse `/bub ...` style content into internal command prompt."""

    body = _strip_prefixed_body(content, prefix=prefix)
    if body is None:
        return None

    words = parse_command_words(body)
    if not words:
        return BubCommandResult(prompt=",help")

    head = words[0].lower()
    tail = words[1:]

    if head == "new":
        return _parse_new_command(tail)
    if head in {"handoff", "anchor"}:
        return BubCommandResult(prompt=_build_handoff_prompt(tail))
    if head in {"help", "tools"}:
        return BubCommandResult(prompt=f",{head}")
    if head in {"info", "anchors", "search", "reset"}:
        mapped = _parse_tape_subcommand(head, tail)
        return BubCommandResult(prompt=mapped) if mapped else None
    if head == "tape":
        mapped = _parse_tape_subcommand(tail[0].lower(), tail[1:]) if tail else ",tape.info"
        return BubCommandResult(prompt=mapped) if mapped else None

    # Keep old behavior: unknown `/bub xxx` still goes to model as text.
    return None


def auto_handoff_name(*, now: datetime | None = None) -> str:
    """Build deterministic timestamped handoff name."""

    moment = now or datetime.now(UTC)
    return f"{AUTO_HANDOFF_NAME_PREFIX}/{moment.strftime('%Y%m%d-%H%M%S')}"


def session_slug(raw: str | None, *, now: datetime | None = None) -> str:
    """Normalize session name for `/bub new` command."""

    if raw:
        candidate = raw.strip().lower()
        normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in candidate).strip("-_")
        if normalized:
            return normalized[:48]
    moment = now or datetime.now(UTC)
    return f"{AUTO_NEW_SESSION_PREFIX}-{moment.strftime('%Y%m%d-%H%M%S')}"


def _parse_new_command(tokens: list[str]) -> BubCommandResult:
    parsed = parse_kv_arguments(tokens)
    requested = _pick_named_value(parsed.kwargs, "name") or (parsed.positional[0] if parsed.positional else None)
    slug = session_slug(requested)
    handoff_name = f"session/new/{slug}/{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    prompt = f",tape.handoff name={shlex.quote(handoff_name)} summary={shlex.quote(f'new session: {slug}')}"
    return BubCommandResult(prompt=prompt, session_name=slug)


def _build_handoff_prompt(tokens: list[str]) -> str:
    parsed = parse_kv_arguments(tokens)
    kwargs: dict[str, object] = dict(parsed.kwargs)

    if "name" not in kwargs:
        kwargs["name"] = parsed.positional[0] if parsed.positional else auto_handoff_name()

    if "summary" not in kwargs and len(parsed.positional) > 1:
        kwargs["summary"] = " ".join(parsed.positional[1:])

    return _format_command("tape.handoff", kwargs)


def _parse_tape_subcommand(head: str, tokens: list[str]) -> str | None:
    if head == "info":
        return ",tape.info"
    if head == "anchors":
        return ",tape.anchors"
    if head == "handoff":
        return _build_handoff_prompt(tokens)
    if head == "search":
        parsed = parse_kv_arguments(tokens)
        kwargs: dict[str, object] = dict(parsed.kwargs)
        if "query" not in kwargs:
            if not parsed.positional:
                return ",tape.search query="
            kwargs["query"] = " ".join(parsed.positional)
        return _format_command("tape.search", kwargs)
    if head == "reset":
        parsed = parse_kv_arguments(tokens)
        kwargs = dict(parsed.kwargs)
        if parsed.positional and "archive" not in kwargs:
            raw = parsed.positional[0].strip().lower()
            if raw in {"1", "true", "yes", "y", "on", "archive"}:
                kwargs["archive"] = True
        return _format_command("tape.reset", kwargs) if kwargs else ",tape.reset"
    return None


def _strip_prefixed_body(content: str, *, prefix: str) -> str | None:
    stripped = content.strip()
    bare_prefix = prefix.rstrip()
    if stripped == bare_prefix:
        return ""
    full_prefix = f"{bare_prefix} "
    if stripped.startswith(full_prefix):
        return stripped[len(full_prefix) :].strip()
    return None


def _format_command(name: str, kwargs: dict[str, object]) -> str:
    if not kwargs:
        return f",{name}"
    tokens = [f",{name}"]
    for key, value in kwargs.items():
        if isinstance(value, bool):
            tokens.append(f"{key}={'true' if value else 'false'}")
            continue
        tokens.append(f"{key}={shlex.quote(str(value))}")
    return " ".join(tokens)


def _pick_named_value(kwargs: dict[str, object], key: str) -> str | None:
    value = kwargs.get(key)
    return value if isinstance(value, str) else None
