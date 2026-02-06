"""Runtime wiring for Bub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from republic import Tool

from ..agent import Agent, Context
from ..config import Settings, get_settings
from ..errors import (
    ApiKeyNotConfiguredError,
    InvalidModelFormatError,
    ModelNotConfiguredError,
    RequiredToolMissingError,
    WorkspaceNotFoundError,
)
from ..tape import TapeService
from ..tools import build_agent_tools, build_cli_tools
from ..tools.catalog import ToolCatalog, build_tool_catalog
from .loop import AgentLoop
from .session import Session

BASH_TOOL_REQUIRED_ERROR = "bash tool is required for shell commands."
WORKSPACE_NOT_FOUND_TEMPLATE = "Workspace directory does not exist: {path}"
MODEL_NOT_CONFIGURED_ERROR = "Model not configured. Set BUB_MODEL (e.g., 'openai:gpt-4o-mini')."
MODEL_FORMAT_ERROR = "Model must be in provider:model format (e.g., 'openai:gpt-4o-mini')."
API_KEY_NOT_CONFIGURED_ERROR = "API key not configured. Set BUB_API_KEY in your environment or .env file."


@dataclass(frozen=True)
class Runtime:
    context: Context
    tool_catalog: ToolCatalog
    tools_cli: list[Tool]
    tools_agent: list[Tool]
    tape: TapeService
    session: Session
    agent_loop: AgentLoop

    @property
    def agent_tool_names(self) -> list[str]:
        return [tool.name for tool in self.tools_agent]

    @classmethod
    def build(
        cls,
        workspace_path: Path,
        *,
        settings: Settings | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> Runtime:
        settings = settings or get_settings(workspace_path)
        _validate_workspace(workspace_path)
        _validate_settings(settings, model_override=model)

        context = Context(workspace_path=workspace_path, settings=settings)
        tool_catalog = build_tool_catalog()
        tools_cli = build_cli_tools(context, tool_catalog)
        tools_agent = build_agent_tools(context, tool_catalog)
        agent = Agent(context=context, model=model, max_tokens=max_tokens, tools=tools_agent)
        tape = TapeService(context.tape_store, context.tape_name)
        bash_tool = _tool_by_name(tools_cli, "bash")
        if bash_tool is None:
            raise RequiredToolMissingError(BASH_TOOL_REQUIRED_ERROR)
        session = Session(
            tools_cli,
            tape,
            workspace_path,
            agent,
            bash_tool=bash_tool,
        )
        agent_loop = AgentLoop(session, tape)

        return cls(
            context=context,
            tool_catalog=tool_catalog,
            tools_cli=tools_cli,
            tools_agent=tools_agent,
            tape=tape,
            session=session,
            agent_loop=agent_loop,
        )


def _tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def _validate_workspace(workspace_path: Path) -> None:
    if not workspace_path.exists():
        message = WORKSPACE_NOT_FOUND_TEMPLATE.format(path=workspace_path)
        raise WorkspaceNotFoundError(message)


def _validate_settings(settings: Settings, *, model_override: str | None) -> None:
    model = model_override or settings.model
    if not model:
        raise ModelNotConfiguredError(MODEL_NOT_CONFIGURED_ERROR)
    if ":" not in model:
        raise InvalidModelFormatError(MODEL_FORMAT_ERROR)
    if not settings.api_key and _requires_api_key(model, settings.api_base):
        raise ApiKeyNotConfiguredError(API_KEY_NOT_CONFIGURED_ERROR)


def _requires_api_key(model: str, api_base: str | None) -> bool:
    provider = model.split(":", 1)[0].lower().strip()
    if api_base:
        return False
    return provider not in {"ollama", "lmstudio", "local"}
