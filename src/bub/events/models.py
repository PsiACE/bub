"""Event model definitions."""

from __future__ import annotations

from abc import ABC
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from .types import EventType, normalize_event_type


class BaseEvent(BaseModel, ABC):
    """Base class for all events in the system.

    All events must inherit from this class and define their event_type.
    """

    event_type: ClassVar[EventType]

    # Allow extra fields for flexibility
    model_config = ConfigDict(extra="allow")

    @classmethod
    def get_event_type_value(cls) -> str:
        """Get the string value of the event type."""
        return normalize_event_type(cls.event_type)

    @classmethod
    def get_domain(cls) -> str:
        """Get the domain this event belongs to."""
        event_value = cls.get_event_type_value()
        return event_value.split(".")[0] if "." in event_value else "unknown"

    @classmethod
    def get_action(cls) -> str:
        """Get the action this event represents."""
        event_value = cls.get_event_type_value()
        return event_value.split(".")[1] if "." in event_value else "unknown"
