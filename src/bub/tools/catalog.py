"""Tool catalog for Bub."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable

from republic import Tool

from ..agent.context import Context
from .adapters import (
    create_bash_tool,
    create_bub_tool,
    create_edit_tool,
    create_glob_tool,
    create_grep_tool,
    create_handoff_tool,
    create_help_tool,
    create_read_tool,
    create_static_tool,
    create_status_tool,
    create_tape_anchors_tool,
    create_tape_info_tool,
    create_tape_reset_tool,
    create_tape_search_tool,
    create_tools_tool,
    create_write_tool,
)

ToolFactory = Callable[[Context, "ToolCatalog"], Tool]
UNKNOWN_AUDIENCE_TEMPLATE = "Unknown tool audience: {audience}"
CORE_PREFIX = "core"
SHORT_PREFIX_MAX_LEN = 3


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    factory: ToolFactory
    show_in_help: bool = False
    agent_tool: bool = True
    cli_tool: bool = True


class ToolCatalog:
    """Registry for tool specs with visibility flags."""

    def __init__(self, specs: Iterable[ToolSpec] | None = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def human_help_specs(self) -> list[ToolSpec]:
        return sorted(
            [spec for spec in self._specs.values() if spec.show_in_help],
            key=lambda spec: spec.name,
        )

    def agent_specs(self) -> list[ToolSpec]:
        return [spec for spec in self._specs.values() if spec.agent_tool]

    def cli_specs(self) -> list[ToolSpec]:
        return [spec for spec in self._specs.values() if spec.cli_tool]

    def build_tools(self, context: Context, *, audience: str) -> list[Tool]:
        if audience == "agent":
            specs = self.agent_specs()
        elif audience == "cli":
            specs = self.cli_specs()
        else:
            message = UNKNOWN_AUDIENCE_TEMPLATE.format(audience=audience)
            raise ValueError(message)
        return [spec.factory(context, self) for spec in specs]

    def render_help(self) -> str:
        specs = self.human_help_specs()
        if not specs:
            return "(no commands)"

        groups: dict[str, list[ToolSpec]] = {}
        for spec in specs:
            prefix = _command_prefix(spec.name)
            groups.setdefault(prefix, []).append(spec)

        lines: list[str] = []
        for prefix in _group_order(groups):
            items = sorted(groups[prefix], key=lambda spec: spec.name)
            if not items:
                continue
            lines.append(_format_group_label(prefix))
            for spec in items:
                if spec.description:
                    lines.append(f"  ${spec.name:13} {spec.description}")
                else:
                    lines.append(f"  ${spec.name}")
            lines.append("")

        lines.append("Shell")
        lines.append("  $<command>      Run a shell command via bash")
        return "\n".join(lines).strip()

    def render_tools(self) -> str:
        specs = sorted(self.agent_specs(), key=lambda spec: spec.name)
        if not specs:
            return "(no tools)"
        return "\n".join(spec.name for spec in specs)

    def render_bub_notice(self, args: list[str]) -> str:
        if args and args[0] == "chat":
            return "Already in chat. Use $tape.reset or $handoff."
        if args and args[0] == "run":
            return "Use bub run from the shell, not inside a session."
        return "Bub is already running. Use $tape.reset or $handoff."


def build_tool_catalog() -> ToolCatalog:
    return ToolCatalog(_all_specs())


def _all_specs() -> list[ToolSpec]:
    return [
        *_filesystem_specs(),
        *_tape_specs(),
        *_meta_specs(),
    ]


def _filesystem_specs() -> list[ToolSpec]:
    return [
        ToolSpec("fs.read", "Read file contents", lambda ctx, _cat: create_read_tool(ctx), show_in_help=True),
        ToolSpec("fs.write", "Write file contents", lambda ctx, _cat: create_write_tool(ctx), show_in_help=True),
        ToolSpec("fs.edit", "Edit file contents", lambda ctx, _cat: create_edit_tool(ctx), show_in_help=True),
        ToolSpec("fs.glob", "List files by glob", lambda ctx, _cat: create_glob_tool(ctx), show_in_help=True),
        ToolSpec("fs.grep", "Search file contents", lambda ctx, _cat: create_grep_tool(ctx), show_in_help=True),
        ToolSpec("bash", "Run a shell command", lambda ctx, _cat: create_bash_tool(ctx)),
    ]


def _tape_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            "tape.search",
            "Search tape entries",
            lambda ctx, _cat: create_tape_search_tool(ctx),
            show_in_help=True,
        ),
        ToolSpec(
            "tape.anchors",
            "List tape anchors",
            lambda ctx, _cat: create_tape_anchors_tool(ctx),
            show_in_help=True,
        ),
        ToolSpec(
            "tape.info",
            "Show tape summary",
            lambda ctx, _cat: create_tape_info_tool(ctx),
            show_in_help=True,
        ),
        ToolSpec(
            "tape.reset",
            "Reset tape",
            lambda ctx, _cat: create_tape_reset_tool(ctx),
            show_in_help=True,
        ),
        ToolSpec("handoff", "Create handoff anchor", lambda ctx, _cat: create_handoff_tool(ctx), show_in_help=True),
        ToolSpec("status", "Show unified status panel", lambda ctx, _cat: create_status_tool(ctx), show_in_help=True),
    ]


def _meta_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            "help", "Show available commands", lambda _ctx, cat: create_help_tool(cat.render_help), show_in_help=True
        ),
        ToolSpec(
            "tools", "Show available tools", lambda _ctx, cat: create_tools_tool(cat.render_tools), show_in_help=True
        ),
        ToolSpec(
            "bub",
            "Show Bub session notice",
            lambda _ctx, cat: create_bub_tool(cat.render_bub_notice),
            agent_tool=False,
        ),
        ToolSpec(
            "quit",
            "End the session",
            lambda _ctx, _cat: create_static_tool("quit", "End the session", "exit"),
            show_in_help=True,
            agent_tool=False,
        ),
        ToolSpec(
            "debug",
            "Toggle debug mode",
            lambda _ctx, _cat: create_static_tool("debug", "Toggle debug mode", "toggle"),
            show_in_help=True,
            agent_tool=False,
        ),
        ToolSpec(
            "done",
            "End the agent run",
            lambda _ctx, _cat: create_static_tool("done", "End the agent run", "done"),
            show_in_help=True,
            agent_tool=False,
        ),
    ]


def _command_prefix(name: str) -> str:
    if "." in name:
        return name.split(".", 1)[0]
    return CORE_PREFIX


def _group_order(groups: dict[str, list[ToolSpec]]) -> list[str]:
    prefixes = sorted(groups.keys())
    if CORE_PREFIX in prefixes:
        prefixes.remove(CORE_PREFIX)
        return [CORE_PREFIX, *prefixes]
    return prefixes


def _format_group_label(prefix: str) -> str:
    if prefix == CORE_PREFIX:
        return "Core"
    if len(prefix) <= SHORT_PREFIX_MAX_LEN:
        return prefix.upper()
    return prefix.title()
