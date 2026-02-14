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

    def all_tools(self) -> list[str]:
        return [descriptor.name for descriptor in self.registry.descriptors()]

    def reset(self) -> None:
        """Clear expanded tool details for a fresh prompt context."""
        self.expanded.clear()

    def note_hint(self, hint: str) -> bool:
        """Expand one tool when hint matches tool name (case-insensitive)."""

        normalized = hint.casefold()
        for descriptor in self.registry.descriptors():
            model_name = self.registry.to_model_name(descriptor.name)
            if descriptor.name.casefold() != normalized and model_name.casefold() != normalized:
                continue
            self.expanded.add(descriptor.name)
            return True
        return False

    def compact_block(self) -> str:
        lines = ["<tool_view>"]
        for row in self.registry.compact_rows(for_model=True):
            lines.append(f"  - {row}")
        lines.append("</tool_view>")
        return "\n".join(lines)

    def expanded_block(self) -> str:
        if not self.expanded:
            return ""

        lines = ["<tool_details>"]
        for name in sorted(self.expanded):
            model_name = self.registry.to_model_name(name)
            try:
                detail = self.registry.detail(name, for_model=True)
            except KeyError:
                continue
            lines.append(f'  <tool name="{model_name}">')
            for line in detail.splitlines():
                lines.append(f"    {line}")
            lines.append("  </tool>")
        lines.append("</tool_details>")
        return "\n".join(lines)
