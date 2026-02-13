"""Shared helpers for builtin hook skills."""

from __future__ import annotations

from bub.types import State


def read_turn(state: State) -> int:
    """Read turn counter from state with tolerant conversion."""

    value = state.get("turn")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0
