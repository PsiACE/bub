"""Utility functions for Bub tools."""

from pathlib import Path
from typing import Union


def sanitize_path(path: Union[str, Path]) -> str:
    """Convert absolute path to relative path from home directory for privacy.

    Args:
        path: The path to sanitize

    Returns:
        A privacy-safe path representation
    """
    path = Path(path).resolve()
    home = Path.home()

    if path == home:
        return "~"
    elif path.is_relative_to(home):
        return str("~" / path.relative_to(home))
    elif path == Path("/"):
        return "/"
    else:
        # For other absolute paths, show relative to current working directory
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            # If not relative to cwd, show just the name
            return path.name or str(path)
