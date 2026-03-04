from typing import Any


def exclude_none(d: dict[str, Any]) -> dict[str, Any]:
    """Exclude None values from a dictionary."""
    return {k: v for k, v in d.items() if v is not None}
