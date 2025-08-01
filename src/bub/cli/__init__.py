"""CLI module with domain-driven event architecture."""

from .app import app
from .controller import CLIDomain
from .render import UIDomain

__all__ = [
    "CLIDomain",
    "UIDomain",
    "app",
]
