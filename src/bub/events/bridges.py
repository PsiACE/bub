"""Domain bridge interface for decoupled event-driven architecture using Pydantic BaseModel events."""

import contextlib
from abc import ABC, abstractmethod
from typing import Any, Optional

import logfire

from ..events.models import BaseEvent
from ..events.system import get_event_system
from ..events.types import EventHandler, EventType, Subscription


class DomainEventBridge(ABC):
    """Abstract interface for domain event emission and handling.

    This allows domains to emit and handle Pydantic BaseEvent instances without
    being tightly coupled to any specific event system or other domains.
    """

    @abstractmethod
    def publish_event(self, event: BaseEvent) -> None:
        """Publish a Pydantic BaseEvent instance."""
        pass

    @abstractmethod
    def subscribe_to_event(self, event_type: EventType, handler: EventHandler, domain: str) -> Subscription:
        """Subscribe to an event type for a domain."""
        pass

    @abstractmethod
    def unsubscribe_from_event(self, subscription: Subscription, domain: str) -> None:
        """Unsubscribe from an event using subscription object."""
        pass

    @abstractmethod
    def get_domain_state(self, domain: str) -> Optional[dict[str, Any]]:
        """Get the current state of a domain."""
        pass

    @abstractmethod
    def set_domain_state(self, domain: str, state: dict[str, Any]) -> None:
        """Set the state of a domain."""
        pass


class NullDomainEventBridge(DomainEventBridge):
    """No-op implementation of DomainEventBridge.

    This is useful for testing or when domains need to work without
    any event system integration.
    """

    def publish_event(self, event: BaseEvent) -> None:
        """No-op event publishing."""
        pass

    def subscribe_to_event(self, event_type: EventType, handler: EventHandler, domain: str) -> Subscription:
        """No-op event subscription."""

        def mock_unsubscribe() -> None:
            pass

        return mock_unsubscribe

    def unsubscribe_from_event(self, subscription: Subscription, domain: str) -> None:
        """No-op event unsubscription."""
        pass

    def get_domain_state(self, domain: str) -> Optional[dict[str, Any]]:
        """No-op state retrieval."""
        return None

    def set_domain_state(self, domain: str, state: dict[str, Any]) -> None:
        """No-op state setting."""
        pass


class LogfireDomainEventBridge(DomainEventBridge):
    """Logfire implementation of DomainEventBridge.

    This bridge logs all domain events and state changes using logfire
    for structured logging and better observability.
    """

    def __init__(self, logger_name: str = "domains") -> None:
        """Initialize the logfire bridge.

        Args:
            logger_name: Name of the logger to use
        """
        self._logger_name = logger_name
        self._state: dict[str, dict[str, Any]] = {}
        self._subscriptions: dict[str, list[Any]] = {}
        self._handlers: dict[str, EventHandler] = {}

    def publish_event(self, event: BaseEvent) -> None:
        """Log event publishing and trigger handlers."""
        event_type = event.get_event_type_value()
        domain = event.get_domain()

        logfire.info(
            "Domain event published",
            domain=domain,
            event_type=event_type,
            logger_name=self._logger_name,
        )

        # Trigger any subscribed handlers for this event type
        for subscription in self._subscriptions.get(event_type, []):
            try:
                handler = self._handlers.get(str(id(subscription)))
                if handler:
                    # Convert BaseEvent to Event for eventure compatibility
                    handler(event)
            except Exception:
                logfire.exception(
                    "Handler failed for event",
                    event_type=event_type,
                    domain=domain,
                    logger_name=self._logger_name,
                )

    def subscribe_to_event(self, event_type: EventType, handler: EventHandler, domain: str) -> Subscription:
        """Log event subscription and store handler."""
        event_type_str = str(event_type.value) if hasattr(event_type, "value") else str(event_type)

        logfire.info(
            "Domain subscribed to event",
            domain=domain,
            event_type=event_type_str,
            logger_name=self._logger_name,
        )

        # Create a subscription function that can be called to unsubscribe
        def subscription() -> None:
            # Remove from subscriptions
            if event_type_str in self._subscriptions:
                with contextlib.suppress(ValueError):
                    self._subscriptions[event_type_str].remove(subscription)

        # Store the handler for later use
        self._handlers[str(id(subscription))] = handler

        if event_type_str not in self._subscriptions:
            self._subscriptions[event_type_str] = []
        self._subscriptions[event_type_str].append(subscription)

        return subscription

    def unsubscribe_from_event(self, subscription: Subscription, domain: str) -> None:
        """Log event unsubscription and remove handler."""
        event_type_str = (
            str(subscription.event_type.value)
            if hasattr(subscription, "event_type") and hasattr(subscription.event_type, "value")
            else str(getattr(subscription, "event_type", "unknown"))
        )

        logfire.info(
            "Domain unsubscribed from event",
            domain=domain,
            event_type=event_type_str,
            logger_name=self._logger_name,
        )

        if event_type_str in self._subscriptions:
            with contextlib.suppress(ValueError):
                self._subscriptions[event_type_str].remove(subscription)

    def get_domain_state(self, domain: str) -> Optional[dict[str, Any]]:
        """Get domain state."""
        return self._state.get(domain)

    def set_domain_state(self, domain: str, state: dict[str, Any]) -> None:
        """Set domain state with structured logging."""
        logfire.info(
            "Domain state updated",
            domain=domain,
            state_keys=list(state.keys()),
            state_size=len(str(state)),
            logger_name=self._logger_name,
        )
        self._state[domain] = state


class EventSystemDomainBridge(DomainEventBridge):
    """Production implementation using the Bub event system.

    This bridge integrates with the existing Bub event system while
    providing the decoupled domain interface.
    """

    def __init__(self, bus_name: str = "default") -> None:
        """Initialize the event system bridge.

        Args:
            bus_name: Name of the event bus to use
        """
        self._event_system = get_event_system()
        self._bus_name = bus_name
        self._state: dict[str, dict[str, Any]] = {}
        self._subscriptions: dict[str, list[Any]] = {}

        # Try to create the bus if it doesn't exist
        with contextlib.suppress(Exception):
            # Check if we can access the adapter to create the bus
            if hasattr(self._event_system, "_adapter") and hasattr(self._event_system._adapter, "create_bus"):
                self._event_system._adapter.create_bus(bus_name)

    def publish_event(self, event: BaseEvent) -> None:
        """Publish event via the event system."""
        try:
            self._event_system.publish(event, bus=self._bus_name)
            logfire.debug(
                "Domain event published via event system",
                domain=event.get_domain(),
                event_type=event.get_event_type_value(),
            )
        except Exception:
            logfire.exception(
                "Failed to publish domain event via event system",
                domain=event.get_domain(),
                event_type=event.get_event_type_value(),
            )

    def subscribe_to_event(self, event_type: EventType, handler: EventHandler, domain: str) -> Subscription:
        """Subscribe to event via the event system."""
        try:
            subscription = self._event_system.subscribe(event_type, handler, bus=self._bus_name)

            # Store subscription for tracking
            domain_key = f"{domain}:{event_type}"
            if domain_key not in self._subscriptions:
                self._subscriptions[domain_key] = []
            self._subscriptions[domain_key].append(subscription)

            logfire.debug(
                "Domain subscribed via event system",
                domain=domain,
                event_type=str(event_type),
            )

        except Exception as e:
            # If subscription fails due to bus not found, create a mock subscription
            logfire.warning(
                "Failed to subscribe via event system, using mock subscription",
                domain=domain,
                event_type=str(event_type),
                error=str(e),
            )

            # Create a mock subscription that does nothing
            def mock_unsubscribe() -> None:
                pass

            subscription = mock_unsubscribe

            # Store subscription for tracking
            domain_key = f"{domain}:{event_type}"
            if domain_key not in self._subscriptions:
                self._subscriptions[domain_key] = []
            self._subscriptions[domain_key].append(subscription)

        return subscription  # type: ignore[return-value]

    def unsubscribe_from_event(self, subscription: Subscription, domain: str) -> None:
        """Unsubscribe from event."""
        try:
            # Remove from tracking
            for _domain_key, subs in self._subscriptions.items():
                if subscription in subs:
                    subs.remove(subscription)
                    break

            # Try to call the unsubscribe function if it's callable
            if callable(subscription):
                with contextlib.suppress(Exception):
                    subscription()

            logfire.debug(
                "Domain unsubscribed via event system",
                domain=domain,
            )

        except Exception:
            logfire.exception(
                "Failed to unsubscribe domain via event system",
                domain=domain,
            )

    def get_domain_state(self, domain: str) -> Optional[dict[str, Any]]:
        """Get domain state."""
        return self._state.get(domain)

    def set_domain_state(self, domain: str, state: dict[str, Any]) -> None:
        """Set domain state."""
        self._state[domain] = state
        logfire.debug(
            "Updated state via event system",
            domain=domain,
            state_keys=list(state.keys()),
        )


class BaseDomain(ABC):
    """Base class for all domains with bridge pattern integration.

    This provides a clean interface for domains to emit Pydantic BaseEvent
    instances and handle state without being coupled to specific event systems.
    """

    def __init__(self, bridge: DomainEventBridge, domain_name: str) -> None:
        """Initialize domain with event bridge.

        Args:
            bridge: Event bridge for communication
            domain_name: Name of this domain
        """
        self._bridge = bridge
        self._domain_name = domain_name
        self._state: dict[str, Any] = {}
        self._subscriptions: list[Subscription] = []
        self._setup_subscriptions()

    @abstractmethod
    def _setup_subscriptions(self) -> None:
        """Setup event subscriptions for this domain."""
        pass

    def publish(self, event: BaseEvent) -> None:
        """Publish an event through the bridge."""
        self._bridge.publish_event(event)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> Subscription:
        """Subscribe to an event type through the bridge."""
        subscription = self._bridge.subscribe_to_event(event_type, handler, self._domain_name)
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from an event through the bridge."""
        self._bridge.unsubscribe_from_event(subscription, self._domain_name)
        with contextlib.suppress(ValueError):
            self._subscriptions.remove(subscription)

    def get_state(self) -> dict[str, Any]:
        """Get the current state of this domain."""
        return self._state.copy()

    def update_state(self, updates: dict[str, Any]) -> None:
        """Update the state of this domain."""
        self._state.update(updates)
        self._bridge.set_domain_state(self._domain_name, self._state)

    def set_state(self, state: dict[str, Any]) -> None:
        """Set the complete state of this domain."""
        self._state = state.copy()
        self._bridge.set_domain_state(self._domain_name, self._state)

    def get_domain_state(self, domain: str) -> Optional[dict[str, Any]]:
        """Get the state of another domain."""
        return self._bridge.get_domain_state(domain)

    def cleanup(self) -> None:
        """Clean up domain resources."""
        for subscription in self._subscriptions:
            self._bridge.unsubscribe_from_event(subscription, self._domain_name)
        self._subscriptions.clear()

    @property
    def domain_name(self) -> str:
        """Get the domain name."""
        return self._domain_name

    @property
    def bridge(self) -> DomainEventBridge:
        """Get the event bridge."""
        return self._bridge
