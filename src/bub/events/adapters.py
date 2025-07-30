"""Event bus adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from eventure import Event, EventBus, EventLog, EventQuery

from .models import BaseEvent
from .types import EventHandler, EventType, Subscription


class EventBusAdapter(ABC):
    """Abstract base class for event bus adapters.

    This interface allows plugging different event bus implementations
    behind a consistent API.
    """

    @abstractmethod
    def publish(
        self,
        event: BaseEvent,
        parent_event: Event | None = None,
        bus_name: str | None = None,
    ) -> Event:
        """Publish an event to the bus.

        Args:
            event: The event to publish
            parent_event: Optional parent event for cascading
            bus_name: Optional bus name to publish to

        Returns:
            Eventure Event object
        """

    @abstractmethod
    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
        bus_name: str | None = None,
    ) -> Subscription:
        """Subscribe to an event type.

        Args:
            event_type: The event type to subscribe to
            handler: The handler function
            bus_name: Optional bus name to subscribe to

        Returns:
            Eventure unsubscribe function
        """

    @abstractmethod
    def subscribe_to_all(
        self,
        handler: EventHandler,
        bus_name: str | None = None,
    ) -> Subscription:
        """Subscribe to all events.

        Args:
            handler: The handler function
            bus_name: Optional bus name to subscribe to

        Returns:
            Eventure unsubscribe function
        """

    @abstractmethod
    def get_bus(self, bus_name: str | None = None) -> EventBus:
        """Get a bus instance.

        Args:
            bus_name: Optional bus name

        Returns:
            Eventure EventBus object
        """

    @abstractmethod
    def get_log(self, bus_name: str | None = None) -> EventLog:
        """Get a log instance for querying events.

        Args:
            bus_name: Optional bus name

        Returns:
            Eventure EventLog object
        """

    @abstractmethod
    def create_bus(self, bus_name: str) -> EventBus:
        """Create a new bus.

        Args:
            bus_name: Name of the bus to create

        Returns:
            Eventure EventBus object
        """

    @abstractmethod
    def get_query(self, bus_name: str | None = None) -> EventQuery:
        """Get a query interface for an event log.

        Args:
            bus_name: Optional bus name

        Returns:
            Eventure EventQuery object
        """


class NullEventBusAdapter(EventBusAdapter):
    """No-op adapter for testing or when events are disabled.

    This adapter implements the interface but performs no operations,
    making it ideal for testing or when event functionality is disabled.
    """

    def publish(
        self,
        event: BaseEvent,
        parent_event: Event | None = None,
        bus_name: str | None = None,
    ) -> Event:
        """No-op publish implementation."""
        raise NotImplementedError("NullEventBusAdapter does not support publishing")

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
        bus_name: str | None = None,
    ) -> Subscription:
        """No-op subscribe implementation."""
        return lambda: None

    def subscribe_to_all(
        self,
        handler: EventHandler,
        bus_name: str | None = None,
    ) -> Subscription:
        """No-op subscribe to all implementation."""
        return lambda: None

    def get_bus(self, bus_name: str | None = None) -> EventBus:
        """Return None bus."""
        raise NotImplementedError("NullEventBusAdapter does not support bus operations")

    def get_log(self, bus_name: str | None = None) -> EventLog:
        """Return None log."""
        raise NotImplementedError("NullEventBusAdapter does not support log operations")

    def create_bus(self, bus_name: str) -> EventBus:
        """Return None bus."""
        raise NotImplementedError("NullEventBusAdapter does not support bus creation")

    def get_query(self, bus_name: str | None = None) -> EventQuery:
        """Return None query."""
        raise NotImplementedError("NullEventBusAdapter does not support query operations")
