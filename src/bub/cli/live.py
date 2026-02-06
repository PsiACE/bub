"""CLI live runner for Bub."""

from __future__ import annotations

import threading
import time
from functools import partial
from typing import Callable

from republic.tape.entries import TapeEntry

from ..runtime import Runtime
from ..tape import LANE_MAIN, LANE_WORK, META_LANE, META_VIEW
from .render import Renderer

FOLLOW_POLL_SECONDS = 0.2
TOOL_PREVIEW_LIMIT = 200


def run_chat(runtime: Runtime, renderer: Renderer) -> None:
    stop_event = threading.Event()
    exit_event = threading.Event()
    request_exit = partial(_request_exit, stop_event, exit_event)
    stop = partial(_stop_chat, renderer, exit_event, request_exit)

    _start_follower(runtime, renderer, request_exit, stop_event)
    runtime.agent_loop.start()
    _run_input_loop(runtime, renderer, exit_event, stop)
    runtime.agent_loop.stop()


def _request_exit(stop_event: threading.Event, exit_event: threading.Event) -> None:
    exit_event.set()
    stop_event.set()


def _stop_chat(
    renderer: Renderer,
    exit_event: threading.Event,
    request_exit: Callable[[], None],
    message: str = "Goodbye!",
) -> None:
    if exit_event.is_set():
        return
    request_exit()
    renderer.info(message)


def _start_follower(
    runtime: Runtime,
    renderer: Renderer,
    request_exit: Callable[[], None],
    stop_event: threading.Event,
) -> None:
    thread = threading.Thread(
        target=_follow_tape,
        args=(runtime, renderer, request_exit, stop_event),
        daemon=True,
    )
    thread.start()


def _follow_tape(
    runtime: Runtime,
    renderer: Renderer,
    request_exit: Callable[[], None],
    stop_event: threading.Event,
) -> None:
    last_seen = -1
    while not stop_event.is_set():
        for entry in runtime.tape.entries():
            if entry.id <= last_seen:
                continue
            last_seen = entry.id
            _handle_entry(entry, renderer, request_exit)
        time.sleep(FOLLOW_POLL_SECONDS)


def _run_input_loop(
    runtime: Runtime,
    renderer: Renderer,
    exit_event: threading.Event,
    stop: Callable[[], None],
) -> None:
    while not exit_event.is_set():
        if runtime.agent_loop.exit_requested:
            stop()
            break
        try:
            user_input = renderer.get_user_input()
        except (KeyboardInterrupt, EOFError):
            stop()
            break
        if not user_input.strip():
            continue
        route = runtime.agent_loop.submit(user_input)
        if route.exit_requested:
            stop()
            break


def _handle_entry(entry: TapeEntry, renderer: Renderer, request_exit: Callable[[], None]) -> None:
    handler = _SPECIAL_HANDLERS.get(entry.kind)
    if handler is not None:
        handler(entry, renderer, request_exit)
        return
    if not _should_render(entry, renderer):
        return
    if entry.kind == "message":
        _render_message(entry, renderer)
        return
    if entry.kind == "anchor":
        _render_anchor(entry, renderer)
        return


def _handle_command(
    entry: TapeEntry,
    renderer: Renderer,
    request_exit: Callable[[], None],
) -> None:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    name = payload.get("name")
    status = payload.get("status")
    stdout = payload.get("stdout") or ""
    stderr = payload.get("stderr") or ""
    if name == "debug" and status == "ok":
        renderer.toggle_debug()
        return
    if name == "quit" and status == "ok":
        request_exit()
        return
    if name == "done":
        return
    if not _should_render(entry, renderer):
        return
    intent = payload.get("intent") or name or "(command)"
    renderer.action_result(str(intent), str(status), str(stdout), str(stderr))


def _handle_tool_entry(
    entry: TapeEntry,
    renderer: Renderer,
    _request_exit: Callable[[], None],
) -> None:
    if not renderer.show_debug:
        return
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    preview = str(payload)
    if len(preview) > TOOL_PREVIEW_LIMIT:
        preview = preview[:TOOL_PREVIEW_LIMIT] + "..."
    renderer.debug_message(f"{entry.kind}: {preview}")


def _handle_loop(
    entry: TapeEntry,
    renderer: Renderer,
    _request_exit: Callable[[], None],
) -> None:
    if not renderer.show_debug:
        return
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    loop_id = payload.get("id", "-")
    status = payload.get("status", "-")
    renderer.debug_message(f"loop: {loop_id} {status}")


def _should_render(entry: TapeEntry, renderer: Renderer) -> bool:
    meta = entry.meta if isinstance(entry.meta, dict) else {}
    if meta.get(META_VIEW) is False:
        return False
    lane = meta.get(META_LANE, LANE_MAIN)
    return lane != LANE_WORK or renderer.show_debug


def _render_message(entry: TapeEntry, renderer: Renderer) -> None:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    role = payload.get("role")
    content = payload.get("content")
    text = content if isinstance(content, str) else str(content)
    if role == "user":
        renderer.user_message(text)
        return
    if role == "assistant":
        cleaned = _strip_control_lines(text)
        if cleaned:
            renderer.assistant_message(cleaned)
        return
    renderer.info(text)


def _render_anchor(entry: TapeEntry, renderer: Renderer) -> None:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    name = payload.get("name", "-")
    state = payload.get("state")
    state_keys = ",".join(sorted(state.keys())) if isinstance(state, dict) else "-"
    renderer.info(f"[anchor] {name} state={state_keys}")


def _strip_control_lines(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() != "$done"]
    return "\n".join(lines).strip()


_SPECIAL_HANDLERS: dict[str, Callable[[TapeEntry, Renderer, Callable[[], None]], None]] = {
    "command": _handle_command,
    "loop": _handle_loop,
    "tool_call": _handle_tool_entry,
    "tool_result": _handle_tool_entry,
}
