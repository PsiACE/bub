"""EventSystem - the main facade for the events framework."""

from __future__ import annotations

from typing import Callable

from eventure import Event, EventBus, EventLog, EventQuery

from .adapters import EventBusAdapter
from .backends.eventure import EventureAdapter
from .models import BaseEvent
from .registry import get_event_schema_or_raise
from .types import EventHandler, EventType, Subscription


class EventSystem:
    """Main facade for the events framework.

    This class provides a clean, high-level API for publishing and subscribing
    to events, while hiding the complexity of the underlying adapter.
    """

    def __init__(self, adapter: EventBusAdapter | None = None) -> None:
        """Initialize the event system.

        Args:
            adapter: Optional event bus adapter. If None, uses EventureAdapter.
        """
        self._adapter = adapter or EventureAdapter()

    def publish(
        self,
        event: BaseEvent | str,
        data: dict[str, str | int | float | bool] | None = None,
        *,
        parent: Event | None = None,
        bus: str = "default",
    ) -> Event:
        """Publish an event.

        Args:
            event: Either a BaseEvent instance or event type string
            data: Event data (only used if event is a string)
            parent: Optional parent event for cascading
            bus: Bus name to publish to

        Returns:
            Eventure Event object

        Raises:
            SchemaNotFoundError: If event type string has no registered schema
        """
        if isinstance(event, str):
            # Create event from string type and data
            event = self._create_event_from_string(event, data)

        return self._adapter.publish(event, parent_event=parent, bus_name=bus)

    def _create_event_from_string(self, event_type: str, data: dict[str, str | int | float | bool] | None) -> BaseEvent:
        """Create an event instance from string type and data.

        Args:
            event_type: The event type string
            data: The event data

        Returns:
            A BaseEvent instance

        Raises:
            SchemaNotFoundError: If no schema is registered for the event type
        """
        event_class = get_event_schema_or_raise(event_type)
        event_data = data or {}
        return event_class(**event_data)

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler | None = None,
        *,
        bus: str = "default",
    ) -> Subscription | Callable[[EventHandler], EventHandler]:
        """Subscribe to an event type.

        Can be used as decorator or direct function call.

        Args:
            event_type: The event type to subscribe to
            handler: Optional handler function (required for direct call)
            bus: Bus name to subscribe to

        Returns:
            Decorator function or subscription object
        """
        if handler is None:
            # Used as decorator
            return self._create_subscription_decorator(event_type, bus)
        else:
            # Direct function call
            return self._adapter.subscribe(event_type, handler, bus_name=bus)

    def _create_subscription_decorator(self, event_type: EventType, bus: str) -> Callable[[EventHandler], EventHandler]:
        """Create a subscription decorator.

        Args:
            event_type: The event type to subscribe to
            bus: Bus name to subscribe to

        Returns:
            Decorator function
        """

        def decorator(func: EventHandler) -> EventHandler:
            self._adapter.subscribe(event_type, func, bus_name=bus)
            return func

        return decorator

    def subscribe_to_all(
        self,
        handler: EventHandler | None = None,
        *,
        bus: str = "default",
    ) -> Subscription | Callable[[EventHandler], EventHandler]:
        """Subscribe to all events.

        Can be used as decorator or direct function call.

        Args:
            handler: Optional handler function (required for direct call)
            bus: Bus name to subscribe to

        Returns:
            Decorator function or subscription object
        """
        if handler is None:
            # Used as decorator
            return self._create_subscribe_all_decorator(bus)
        else:
            # Direct function call
            return self._adapter.subscribe_to_all(handler, bus_name=bus)

    def _create_subscribe_all_decorator(self, bus: str) -> Callable[[EventHandler], EventHandler]:
        """Create a subscribe-to-all decorator.

        Args:
            bus: Bus name to subscribe to

        Returns:
            Decorator function
        """

        def decorator(func: EventHandler) -> EventHandler:
            self._adapter.subscribe_to_all(func, bus_name=bus)
            return func

        return decorator

    def get_bus(self, name: str = "default") -> EventBus:
        """Get a bus instance.

        Args:
            name: Bus name

        Returns:
            Eventure EventBus object
        """
        return self._adapter.get_bus(name)

    def get_log(self, name: str = "default") -> EventLog:
        """Get a log instance.

        Args:
            name: Bus name

        Returns:
            Eventure EventLog object
        """
        return self._adapter.get_log(name)

    def create_bus(self, name: str) -> EventBus:
        """Create a new bus.

        Args:
            name: Name of the bus to create

        Returns:
            Eventure EventBus object
        """
        return self._adapter.create_bus(name)

    def get_query(self, name: str = "default") -> EventQuery:
        """Get a query interface for an event log.

        Args:
            name: Bus name

        Returns:
            Eventure EventQuery object
        """
        return self._adapter.get_query(name)


# Global event system instance - singleton pattern
_global_event_system: EventSystem | None = None


def get_event_system() -> EventSystem:
    """Get the global event system instance.

    Returns:
        The global EventSystem instance
    """
    global _global_event_system
    if _global_event_system is None:
        _global_event_system = EventSystem()
    return _global_event_system


def set_event_system(event_system: EventSystem) -> None:
    """Set the global event system instance.

    Args:
        event_system: The EventSystem instance to set as global
    """
    global _global_event_system
    _global_event_system = event_system
