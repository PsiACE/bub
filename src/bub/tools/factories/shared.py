"""Shared tool input models and context helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.context import Context
from ...tape import TapeService


class ReadInput(BaseModel):
    """Read a file with optional offset and limit."""

    path: str = Field(..., description="Path to the file")
    offset: int = Field(default=0, description="Line offset (0-based)")
    limit: int | None = Field(default=None, description="Maximum number of lines to read")


class WriteInput(BaseModel):
    """Write content to a file."""

    path: str = Field(..., description="Path to the file")
    content: str = Field(..., description="File contents")


class EditInput(BaseModel):
    """Replace text in a file."""

    path: str = Field(..., description="Path to the file")
    old: str = Field(..., description="Text to replace")
    new: str = Field(..., description="Replacement text")
    all: bool = Field(default=False, description="Replace all occurrences")


class GlobInput(BaseModel):
    """Find files matching a glob pattern."""

    path: str = Field(default=".", description="Base path")
    pattern: str = Field(..., description="Glob pattern")


class GrepInput(BaseModel):
    """Search for a regex pattern in files."""

    pattern: str = Field(..., description="Regex pattern")
    path: str = Field(default=".", description="Base path")


class BashInput(BaseModel):
    """Run a shell command."""

    cmd: str = Field(..., description="Shell command to run")
    cwd: str | None = Field(default=None, description="Working directory")


class TapeSearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    after: str | None = Field(default=None, description="Anchor name")
    limit: int | None = Field(default=None, description="Limit matches")
    case_sensitive: bool = Field(default=False, description="Case-sensitive search")


class TapeAnchorsInput(BaseModel):
    limit: int | None = Field(default=None, description="Limit anchors")


class TapeResetInput(BaseModel):
    archive: bool = Field(default=False, description="Archive before reset")


class HandoffInput(BaseModel):
    name: str | None = Field(default=None, description="Anchor name")
    summary: str | None = Field(default=None, description="Summary")
    next_steps: str | None = Field(default=None, description="Next steps")


class EmptyInput(BaseModel):
    """Empty input payload."""


class StatusInput(BaseModel):
    debug: bool = Field(default=False, description="Include recent command list")


class BubInput(BaseModel):
    args: list[str] = Field(default_factory=list, description="Command arguments")


class WebFetchInput(BaseModel):
    """Fetch a web page and convert the HTML body to markdown."""

    url: str = Field(..., description="URL to fetch")


class WebSearchInput(BaseModel):
    """Run a web search query via Ollama web search API."""

    query: str = Field(..., description="Search query")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum search results")


def resolve_path(context: Context, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return context.workspace_path / path


def tape_service(context: Context) -> TapeService:
    return TapeService(context.tape_store, context.tape_name)
