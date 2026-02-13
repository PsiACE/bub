"""Pluggy hook namespace and framework hook specifications."""

from __future__ import annotations

from typing import Any

import pluggy

from bub.bus import BusProtocol
from bub.types import Envelope, State

BUB_HOOK_NAMESPACE = "bub"
hookspec = pluggy.HookspecMarker(BUB_HOOK_NAMESPACE)
hookimpl = pluggy.HookimplMarker(BUB_HOOK_NAMESPACE)


class BubHookSpecs:
    """Hook contract for Bub framework extensions."""

    @hookspec(firstresult=True)
    def provide_bus(self) -> BusProtocol | None:
        """Provide a bus instance for inbound/outbound envelopes."""

    @hookspec(firstresult=True)
    def normalize_inbound(self, message: Envelope) -> Envelope | None:
        """Normalize or rewrite one inbound message."""

    @hookspec(firstresult=True)
    def resolve_session(self, message: Envelope) -> str | None:
        """Resolve session id for one inbound message."""

    @hookspec(firstresult=True)
    def load_state(self, session_id: str) -> State | None:
        """Load state snapshot for one session."""

    @hookspec(firstresult=True)
    def build_prompt(self, message: Envelope, session_id: str, state: State) -> str | None:
        """Build model prompt for this turn."""

    @hookspec(firstresult=True)
    def run_model(self, prompt: str, session_id: str, state: State) -> str | None:
        """Run model for one turn and return plain text output."""

    @hookspec
    def save_state(
        self,
        session_id: str,
        state: State,
        message: Envelope,
        model_output: str,
    ) -> None:
        """Persist state updates after one model turn."""

    @hookspec
    def render_outbound(
        self,
        message: Envelope,
        session_id: str,
        state: State,
        model_output: str,
    ) -> list[Envelope] | None:
        """Render outbound messages from model output."""

    @hookspec
    def dispatch_outbound(self, message: Envelope) -> bool | None:
        """Dispatch one outbound message to external channel(s)."""

    @hookspec
    def register_cli_commands(self, app: Any) -> None:
        """Register CLI commands onto the root Typer application."""

    @hookspec
    def on_error(self, stage: str, error: Exception, message: Envelope | None) -> None:
        """Observe framework errors from any stage."""
