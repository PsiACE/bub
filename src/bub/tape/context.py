"""Tape context helpers."""

from __future__ import annotations

from republic import TapeContext


def default_tape_context() -> TapeContext:
    """Return the default context selection for Bub."""

    return TapeContext()
