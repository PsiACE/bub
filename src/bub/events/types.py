"""Event type definitions and utilities."""

from __future__ import annotations

from enum import Enum
from typing import Callable, TypeVar, Union

from eventure import Event

# Type aliases for better readability and consistency
EventType = Union[str, Enum]
EventHandler = Callable[[Event], None]
Subscription = Callable[[], None]  # Eventure returns unsubscribe function

# Type variable for event classes
EventT = TypeVar("EventT")  # Will be bound to BaseEvent when imported


class DomainEventType(str, Enum):
    """Base class for domain event types with standardized naming.

    Event types should follow the pattern 'domain.action' for consistency.
    """

    @property
    def domain(self) -> str:
        """Extract domain from event type."""
        return str(self.value).split(".")[0]

    @property
    def action(self) -> str:
        """Extract action from event type."""
        return str(self.value).split(".")[1]


def normalize_event_type(event_type: EventType) -> str:
    """Normalize event type to string representation.

    Args:
        event_type: Event type as string or Enum

    Returns:
        Normalized string representation
    """
    if isinstance(event_type, Enum):
        return str(event_type.value)
    return str(event_type)


def is_valid_event_type(event_type: EventType) -> bool:
    """Validate event type format.

    Args:
        event_type: Event type to validate

    Returns:
        True if valid, False otherwise
    """
    normalized = normalize_event_type(event_type)
    return bool(normalized and "." in normalized)
