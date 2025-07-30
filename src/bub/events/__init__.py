"""Events Framework - A standalone event system for Bub.

This framework provides a clean, adapter-based event system that can work
with different backends (currently eventure, but extensible).

Public API:
    - EventSystem: Main facade for publishing/subscribing
    - BaseEvent: Base class for all events
    - register_event: Decorator for registering event schemas
    - get_event_system: Get global event system instance
    - DomainEventType: Base for domain event types

Usage:
    from bub.events import EventSystem, BaseEvent, register_event

    @register_event
    class MyEvent(BaseEvent):
        event_type = MyEventType.SOMETHING
        data: str

    system = EventSystem()
    system.publish(MyEvent(data="hello"))

    @system.subscribe(MyEventType.SOMETHING)
    def handle_event(event):
        print(f"Got: {event.data}")
"""

from typing import Callable

from eventure import Event, EventBus, EventLog, EventQuery

from .adapters import EventBusAdapter, NullEventBusAdapter
from .exceptions import (
    BusNotFoundError,
    EventAdapterError,
    EventBusError,
    EventError,
    EventSubscriptionError,
    EventTypeError,
    EventValidationError,
    SchemaNotFoundError,
)
from .models import BaseEvent
from .registry import get_event_schema, get_event_schema_or_raise, register_event
from .system import EventSystem, get_event_system, set_event_system
from .types import DomainEventType, EventHandler, EventType, Subscription


# Convenience functions using global event system
def publish(
    event: BaseEvent | str,
    data: dict[str, str | int | float | bool] | None = None,
    *,
    parent: Event | None = None,
    bus: str = "default",
) -> Event:
    """Publish an event using the global event system.

    Args:
        event: Either a BaseEvent instance or event type string
        data: Event data (only used if event is a string)
        parent: Optional parent event for cascading
        bus: Bus name to publish to

    Returns:
        Eventure Event object

    """
    return get_event_system().publish(event, data, parent=parent, bus=bus)


def subscribe(
    event_type: EventType,
    handler: EventHandler | None = None,
    *,
    bus: str = "default",
) -> Subscription | Callable[[EventHandler], EventHandler]:
    """Subscribe to an event type using the global event system.

    Args:
        event_type: The event type to subscribe to
        handler: Optional handler function (required for direct call)
        bus: Bus name to subscribe to

    Returns:
        Decorator function or subscription object

    """
    return get_event_system().subscribe(event_type, handler, bus=bus)


def subscribe_to_all(
    handler: EventHandler | None = None,
    *,
    bus: str = "default",
) -> Subscription | Callable[[EventHandler], EventHandler]:
    """Subscribe to all events using the global event system.

    Args:
        handler: Optional handler function (required for direct call)
        bus: Bus name to subscribe to

    Returns:
        Decorator function or subscription object

    """
    return get_event_system().subscribe_to_all(handler, bus=bus)


def get_bus(name: str = "default") -> EventBus:
    """Get a bus instance from the global event system.

    Args:
        name: Bus name

    Returns:
        Eventure EventBus object

    """
    return get_event_system().get_bus(name)


def get_log(name: str = "default") -> EventLog:
    """Get a log instance from the global event system.

    Args:
        name: Bus name

    Returns:
        Eventure EventLog object

    """
    return get_event_system().get_log(name)


def get_query(name: str = "default") -> EventQuery:
    """Get a query interface from the global event system.

    Args:
        name: Bus name

    Returns:
        Eventure EventQuery object

    """
    return get_event_system().get_query(name)


def create_bus(name: str) -> EventBus:
    """Create a new bus in the global event system.

    Args:
        name: Name of the bus to create

    Returns:
        Eventure EventBus object

    """
    return get_event_system().create_bus(name)


# Public API exports
__all__ = [  # noqa: RUF022
    # Core classes
    "EventSystem",
    "BaseEvent",
    "DomainEventType",
    # Registration
    "register_event",
    "get_event_schema",
    "get_event_schema_or_raise",
    # Global system
    "get_event_system",
    "set_event_system",
    # Types
    "EventType",
    "EventHandler",
    "Subscription",
    # Adapters
    "EventBusAdapter",
    "NullEventBusAdapter",
    # Exceptions
    "BusNotFoundError",
    "SchemaNotFoundError",
    "EventError",
    "EventTypeError",
    "EventBusError",
    "EventSubscriptionError",
    "EventValidationError",
    "EventAdapterError",
    # Convenience functions
    "publish",
    "subscribe",
    "subscribe_to_all",
    "get_bus",
    "get_log",
    "get_query",
    "create_bus",
]
