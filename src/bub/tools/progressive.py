"""Progressive tool prompt rendering."""

from __future__ import annotations

from dataclasses import dataclass, field

from bub.tools.registry import ToolRegistry


@dataclass
class ProgressiveToolView:
    """Renders compact tool view and expands schema on demand."""

    registry: ToolRegistry
    expanded: set[str] = field(default_factory=set)

    def note_selected(self, name: str) -> None:
        if self.registry.has(name):
            self.expanded.add(name)

    def note_hint(self, hint: str) -> bool:
        """Expand one tool when hint matches tool name (case-insensitive)."""

        normalized = hint.casefold()
        for descriptor in self.registry.descriptors():
            if descriptor.name.casefold() != normalized:
                continue
            self.expanded.add(descriptor.name)
            return True
        return False

    def compact_block(self) -> str:
        lines = ["<tool_view>"]
        for row in self.registry.compact_rows():
            lines.append(f"  - {row}")
        lines.append("</tool_view>")
        return "\n".join(lines)

    def expanded_block(self) -> str:
        if not self.expanded:
            return ""

        lines = ["<tool_details>"]
        for name in sorted(self.expanded):
            try:
                detail = self.registry.detail(name)
            except KeyError:
                continue
            lines.append(f'  <tool name="{name}">')
            for line in detail.splitlines():
                lines.append(f"    {line}")
            lines.append("  </tool>")
        lines.append("</tool_details>")
        return "\n".join(lines)
