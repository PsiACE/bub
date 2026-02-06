"""Tape-centric tool factories."""

from __future__ import annotations

from republic import Tool, tool_from_model

from ...agent.context import Context
from .shared import (
    EmptyInput,
    HandoffInput,
    StatusInput,
    TapeAnchorsInput,
    TapeResetInput,
    TapeSearchInput,
    tape_service,
)


def create_tape_search_tool(context: Context) -> Tool:
    def _handler(params: TapeSearchInput) -> str:
        tape = tape_service(context)
        return tape.search(
            params.query,
            after=params.after,
            limit=params.limit,
            case_sensitive=params.case_sensitive,
        )

    return tool_from_model(
        TapeSearchInput,
        _handler,
        name="tape.search",
        description="Search tape entries",
    )


def create_tape_anchors_tool(context: Context) -> Tool:
    def _handler(params: TapeAnchorsInput) -> str:
        return tape_service(context).anchors(limit=params.limit)

    return tool_from_model(
        TapeAnchorsInput,
        _handler,
        name="tape.anchors",
        description="List tape anchors",
    )


def create_tape_info_tool(context: Context) -> Tool:
    def _handler(_params: EmptyInput) -> str:
        return tape_service(context).info()

    return tool_from_model(
        EmptyInput,
        _handler,
        name="tape.info",
        description="Show tape summary",
    )


def create_tape_reset_tool(context: Context) -> Tool:
    def _handler(params: TapeResetInput) -> str:
        return tape_service(context).reset(archive=params.archive)

    return tool_from_model(
        TapeResetInput,
        _handler,
        name="tape.reset",
        description="Reset tape (optionally archive)",
    )


def create_handoff_tool(context: Context) -> Tool:
    def _handler(params: HandoffInput) -> str:
        tape = tape_service(context)
        entry = tape.handoff(
            params.name,
            summary=params.summary,
            next_steps=params.next_steps,
        )
        return f"ok: {entry.payload.get('name', '-')}"

    return tool_from_model(
        HandoffInput,
        _handler,
        name="handoff",
        description="Create a handoff anchor",
    )


def create_status_tool(context: Context) -> Tool:
    def _handler(params: StatusInput) -> str:
        return tape_service(context).status_panel(debug=params.debug)

    return tool_from_model(
        StatusInput,
        _handler,
        name="status",
        description="Show unified status panel",
    )
