"""Background agent loop runner."""

from __future__ import annotations

import queue
import threading
import time
import uuid

from ..tape import TapeService
from .session import Session

MAX_AGENT_STEPS = 100
QUEUE_POLL_SECONDS = 0.2
AGENT_STEP_DELAY_SECONDS = 0.05


class AgentLoop:
    """Run the agent in background turns until completion markers are hit."""

    def __init__(
        self,
        session: Session,
        tape: TapeService,
        *,
        max_steps: int = MAX_AGENT_STEPS,
    ) -> None:
        self._session = session
        self._tape = tape
        self._max_steps = max_steps
        self._queue: queue.Queue[None] = queue.Queue()
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._loop_active = threading.Event()
        self._exit_requested = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def exit_requested(self) -> bool:
        return self._exit_requested.is_set()

    def submit(self, raw: str):
        result = self._session.handle_input(raw, origin="human")
        if result.exit_requested:
            self._exit_requested.set()
            self.stop()
            return result
        if result.done_requested:
            if self._loop_active.is_set():
                self._done_event.set()
            return result
        if result.enter_agent:
            self._queue.put(None)
        return result

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._queue.get(timeout=QUEUE_POLL_SECONDS)
            except queue.Empty:
                continue
            self._run_loop()
            self._queue.task_done()

    def _run_loop(self) -> None:
        loop_id = uuid.uuid4().hex[:8]
        self._tape.record_loop(loop_id, "start")
        self._loop_active.set()
        steps = 0

        try:
            while not self._stop_event.is_set():
                if self._done_event.is_set():
                    self._done_event.clear()
                    self._tape.record_loop(loop_id, "done")
                    return

                response = self._session.agent_respond(on_event=self._record_tool_event)
                assistant_result = self._session.interpret_assistant(response)
                if assistant_result.visible_text:
                    self._tape.record_assistant_message(assistant_result.visible_text)
                if assistant_result.exit_requested:
                    self._tape.record_loop(loop_id, "exit")
                    self._exit_requested.set()
                    return
                if assistant_result.done_requested:
                    self._tape.record_loop(loop_id, "done")
                    return

                followup = assistant_result.followup_input.strip()
                # End the loop when the assistant returns plain text without follow-up commands.
                if not followup:
                    self._tape.record_loop(loop_id, "idle")
                    return

                steps += 1
                if steps >= self._max_steps:
                    self._tape.record_loop(loop_id, "max_steps")
                    return

                self._tape.record_context_message(followup)
                time.sleep(AGENT_STEP_DELAY_SECONDS)
        finally:
            self._loop_active.clear()
            self._done_event.clear()

    def _record_tool_event(self, event) -> None:
        self._tape.record_tool_event(event.kind, event.payload)
