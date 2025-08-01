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


def pretty_path(path: Union[str, Path]) -> str:
    """Convert path to a pretty display format, replacing home directory with ~.

    Inspired by crush's PrettyPath function.

    Args:
        path: The path to prettify

    Returns:
        A pretty path representation
    """
    path = Path(path).resolve()
    home = Path.home()

    if path == home:
        return "~"
    elif path.is_relative_to(home):
        return str("~" / path.relative_to(home))
    else:
        return str(path)


def dir_trim(pwd: Union[str, Path], limit: int) -> str:
    """Trim directory path for display purposes.

    Inspired by crush's DirTrim function.

    Args:
        pwd: The path to trim
        limit: Maximum number of directory levels to show

    Returns:
        A trimmed path representation
    """
    pwd = Path(pwd).resolve()
    home = Path.home()

    # If path is in home directory, start with ~
    if pwd.is_relative_to(home):
        pwd = Path("~") / pwd.relative_to(home)

    parts = pwd.parts

    if limit <= 0 or limit >= len(parts) - 1:
        return str(pwd)

    # Keep the last 'limit' parts, replace others with ...
    if len(parts) <= limit + 1:
        return str(pwd)

    # For absolute paths, keep the root
    if pwd.is_absolute():
        result_parts = [parts[0]]  # Keep root
        for _ in range(1, len(parts) - limit + 1):
            result_parts.append("...")
        result_parts.extend(parts[-(limit - 1) :])
    else:
        # For relative paths
        result_parts = ["..."]
        result_parts.extend(parts[-(limit):])

    return str(Path(*result_parts))


def is_hidden_file(path: Union[str, Path]) -> bool:
    """Check if a file or directory is hidden.

    Args:
        path: The path to check

    Returns:
        True if the file/directory is hidden
    """
    path = Path(path)
    return path.name.startswith(".")


def get_file_size_display(size_bytes: int) -> str:
    """Convert file size in bytes to human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size_float = float(size_bytes)
    while size_float >= 1024 and i < len(size_names) - 1:
        size_float = size_float / 1024.0
        i += 1

    return f"{size_float:.1f} {size_names[i]}"


def normalize_path(path: Union[str, Path]) -> Path:
    """Normalize a path, resolving any symlinks and making it absolute.

    Args:
        path: The path to normalize

    Returns:
        Normalized Path object
    """
    return Path(path).resolve()


def is_within_directory(directory: Union[str, Path], path: Union[str, Path]) -> bool:
    """Check if a path is within a directory.

    Args:
        directory: The directory to check within
        path: The path to check

    Returns:
        True if the path is within the directory
    """
    try:
        directory = Path(directory).resolve()
        path = Path(path).resolve()
        path.relative_to(directory)
    except ValueError:
        return False

    return True


def safe_filename(filename: str) -> str:
    """Convert a string to a safe filename.

    Args:
        filename: The filename to sanitize

    Returns:
        A safe filename
    """
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing spaces and dots
    filename = filename.strip(" .")

    # Ensure it's not empty
    if not filename:
        filename = "unnamed"

    return filename
