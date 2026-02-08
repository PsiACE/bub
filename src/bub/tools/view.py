"""Tool view helpers."""

from __future__ import annotations

from bub.tools.progressive import ProgressiveToolView


def render_tool_prompt_block(view: ProgressiveToolView) -> str:
    """Render the combined tool prompt section."""

    compact = view.compact_block()
    expanded = view.expanded_block()
    if not expanded:
        return compact
    return f"{compact}\n\n{expanded}"
