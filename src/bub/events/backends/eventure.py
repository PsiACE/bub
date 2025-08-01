"""Eventure backend adapter."""

from __future__ import annotations

from eventure import Event, EventBus, EventLog, EventQuery

from ..exceptions import BusAlreadyExistsError, BusNotFoundError
from ..models import BaseEvent
from ..types import EventHandler, EventType, Subscription, normalize_event_type


class EventureAdapter:
    """Clean adapter for the eventure event system backend.

    This adapter encapsulates all eventure-specific logic and provides
    a clean interface that matches our event system API.
    """

    def __init__(self) -> None:
        """Initialize the eventure adapter."""
        self._event_buses: dict[str, EventBus] = {}
        self._event_logs: dict[str, EventLog] = {}
        self._default_bus_name = "default"

        # Create default bus
        self._create_event_bus(self._default_bus_name)

    def _create_event_bus(self, name: str) -> EventBus:
        """Create a new event bus.

        Args:
            name: Name of the bus to create

        Returns:
            The created EventBus instance

        Raises:
            BusAlreadyExistsError: If bus already exists
        """
        if name in self._event_buses:
            raise BusAlreadyExistsError(name)

        event_log = EventLog()
        event_bus = EventBus(event_log)

        self._event_buses[name] = event_bus
        self._event_logs[name] = event_log

        return event_bus

    def _get_target_bus_name(self, bus_name: str | None) -> str:
        """Get the target bus name, defaulting to default bus."""
        return bus_name or self._default_bus_name

    def _ensure_bus_exists(self, bus_name: str) -> None:
        """Ensure a bus exists, raising error if not.

        Args:
            bus_name: Name of the bus to check

        Raises:
            BusNotFoundError: If bus doesn't exist
        """
        if bus_name not in self._event_buses:
            raise BusNotFoundError(bus_name)

    def publish(
        self,
        event: BaseEvent,
        parent_event: Event | None = None,
        bus_name: str | None = None,
    ) -> Event:
        """Publish an event to the eventure bus.

        Args:
            event: The event to publish
            parent_event: Optional parent event for cascading
            bus_name: Optional bus name to publish to

        Returns:
            The published eventure Event object

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        target_bus_name = self._get_target_bus_name(bus_name)
        self._ensure_bus_exists(target_bus_name)

        event_bus = self._event_buses[target_bus_name]

        # Use the bus publish method which handles Event creation
        return event_bus.publish(
            event.get_event_type_value(),
            event.model_dump(),
            parent_event=parent_event,
        )

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
            The subscription object

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        target_bus_name = self._get_target_bus_name(bus_name)
        self._ensure_bus_exists(target_bus_name)

        event_bus = self._event_buses[target_bus_name]

        # Normalize event type to string
        normalized_type = normalize_event_type(event_type)

        return event_bus.subscribe(normalized_type, handler)  # type: ignore[arg-type]

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
            The subscription object

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        target_bus_name = self._get_target_bus_name(bus_name)
        self._ensure_bus_exists(target_bus_name)

        event_bus = self._event_buses[target_bus_name]

        # Eventure doesn't have subscribe_to_all, so we use a wildcard pattern
        # Subscribe to all domains by using "*" pattern
        return event_bus.subscribe("*", handler)  # type: ignore[arg-type]

    def get_bus(self, bus_name: str | None = None) -> EventBus:
        """Get a bus instance.

        Args:
            bus_name: Optional bus name

        Returns:
            The EventBus instance

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        target_bus_name = self._get_target_bus_name(bus_name)
        self._ensure_bus_exists(target_bus_name)

        return self._event_buses[target_bus_name]

    def get_log(self, bus_name: str | None = None) -> EventLog:
        """Get a log instance for querying events.

        Args:
            bus_name: Optional bus name

        Returns:
            The EventLog instance

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        target_bus_name = self._get_target_bus_name(bus_name)

        if target_bus_name not in self._event_logs:
            raise BusNotFoundError(target_bus_name)

        return self._event_logs[target_bus_name]

    def create_bus(self, bus_name: str) -> EventBus:
        """Create a new bus.

        Args:
            bus_name: Name of the bus to create

        Returns:
            The created EventBus instance

        Raises:
            BusAlreadyExistsError: If bus already exists
        """
        return self._create_event_bus(bus_name)

    def get_query(self, bus_name: str | None = None) -> EventQuery:
        """Get a query interface for an event log.

        Args:
            bus_name: Optional bus name

        Returns:
            The EventQuery instance

        Raises:
            BusNotFoundError: If specified bus doesn't exist
        """
        event_log = self.get_log(bus_name)
        return EventQuery(event_log)
