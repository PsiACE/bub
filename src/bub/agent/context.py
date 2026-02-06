"""Context for the agent package."""

from pathlib import Path

from ..config import Settings, get_settings
from ..tape import DEFAULT_TAPE_NAME, FileTapeStore


class Context:
    """Agent environment context: workspace and settings."""

    def __init__(self, workspace_path: Path | str | None = None, settings: Settings | None = None) -> None:
        resolved_path = Path.cwd() if workspace_path is None else Path(workspace_path)
        self.workspace_path = resolved_path
        self.settings = settings or get_settings(self.workspace_path)
        self.tape_name = DEFAULT_TAPE_NAME
        self.tape_store = FileTapeStore(self.workspace_path, tape_name=self.tape_name)
