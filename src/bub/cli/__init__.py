"""CLI module with domain-driven event architecture."""

from .app import app
from .domain import CLIDomain
from .ui import UIDomain

__all__ = [
    "CLIDomain",
    "UIDomain",
    "app",
]
