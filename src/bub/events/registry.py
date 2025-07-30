"""Event schema registry and management."""

from __future__ import annotations

from .exceptions import SchemaNotFoundError
from .models import BaseEvent
from .types import EventType, normalize_event_type


class EventSchemaRegistry:
    """Registry for event schemas and validation."""

    def __init__(self) -> None:
        """Initialize the event schema registry."""
        self._schemas: dict[str, type[BaseEvent]] = {}
        self._schemas_by_class: dict[type[BaseEvent], str] = {}

    def register(self, event_class: type[BaseEvent]) -> type[BaseEvent]:
        """Register an event class.

        Args:
            event_class: The event class to register

        Returns:
            The same event class (for decorator usage)

        Raises:
            ValueError: If event type is already registered with different class
        """
        event_type = event_class.get_event_type_value()

        if event_type in self._schemas:
            existing = self._schemas[event_type]
            if existing != event_class:
                msg = (
                    f"Event type '{event_type}' already registered with different class: "
                    f"{existing.__name__} vs {event_class.__name__}"
                )
                raise ValueError(msg)
        else:
            self._schemas[event_type] = event_class
            self._schemas_by_class[event_class] = event_type

        return event_class

    def get_schema(self, event_type: EventType) -> type[BaseEvent] | None:
        """Get the schema for an event type.

        Args:
            event_type: The event type (string or Enum)

        Returns:
            The event class or None if not found
        """
        normalized_type = normalize_event_type(event_type)
        return self._schemas.get(normalized_type)

    def get_schema_or_raise(self, event_type: EventType) -> type[BaseEvent]:
        """Get the schema for an event type, raising exception if not found.

        Args:
            event_type: The event type (string or Enum)

        Returns:
            The event class

        Raises:
            SchemaNotFoundError: If schema not found
        """
        schema = self.get_schema(event_type)
        if schema is None:
            normalized_type = normalize_event_type(event_type)
            raise SchemaNotFoundError(normalized_type)
        return schema

    def list_schemas(self) -> dict[str, type[BaseEvent]]:
        """List all registered schemas.

        Returns:
            dictionary mapping event types to their classes
        """
        return self._schemas.copy()

    def is_registered(self, event_type: EventType) -> bool:
        """Check if an event type is registered.

        Args:
            event_type: The event type to check

        Returns:
            True if registered, False otherwise
        """
        return normalize_event_type(event_type) in self._schemas

    def unregister(self, event_type: EventType) -> bool:
        """Unregister an event type.

        Args:
            event_type: The event type to unregister

        Returns:
            True if was registered and removed, False otherwise
        """
        normalized_type = normalize_event_type(event_type)
        if normalized_type in self._schemas:
            event_class = self._schemas[normalized_type]
            del self._schemas[normalized_type]
            self._schemas_by_class.pop(event_class, None)
            return True
        return False


# Global schema registry - singleton pattern
_global_registry = EventSchemaRegistry()


def register_event(event_class: type[BaseEvent]) -> type[BaseEvent]:
    """Register an event class with the global schema registry.

    This is a decorator that can be used to register event classes.

    Args:
        event_class: The event class to register

    Returns:
        The same event class (for decorator usage)
    """
    return _global_registry.register(event_class)


def get_event_schema(event_type: EventType) -> type[BaseEvent] | None:
    """Get the schema for an event type from global registry.

    Args:
        event_type: The event type (string or Enum)

    Returns:
        The event class or None if not found
    """
    return _global_registry.get_schema(event_type)


def get_event_schema_or_raise(event_type: EventType) -> type[BaseEvent]:
    """Get the schema for an event type, raising exception if not found.

    Args:
        event_type: The event type (string or Enum)

    Returns:
        The event class

    Raises:
        SchemaNotFoundError: If schema not found
    """
    return _global_registry.get_schema_or_raise(event_type)


def get_registry() -> EventSchemaRegistry:
    """Get the global event schema registry.

    Returns:
        The global EventSchemaRegistry instance
    """
    return _global_registry
