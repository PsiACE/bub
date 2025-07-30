"""Event framework exceptions with clean hierarchy."""


class EventError(Exception):
    """Base exception for event-related errors."""


class EventTypeError(EventError):
    """Exception for event type validation errors."""


class EventBusError(EventError):
    """Exception for event bus operation errors."""


class EventSubscriptionError(EventError):
    """Exception for event subscription errors."""


class EventValidationError(EventError):
    """Exception for event validation errors."""


class EventAdapterError(EventError):
    """Exception for event adapter errors."""


class BusNotFoundError(EventBusError):
    """Exception for when a specific event bus is not found."""

    def __init__(self, bus_name: str) -> None:
        """Initialize with bus name."""
        super().__init__(f"Event bus '{bus_name}' not found")
        self.bus_name = bus_name


class BusAlreadyExistsError(EventBusError):
    """Exception for when trying to create a bus that already exists."""

    def __init__(self, bus_name: str) -> None:
        """Initialize with bus name."""
        super().__init__(f"Event bus '{bus_name}' already exists")
        self.bus_name = bus_name


class SchemaNotFoundError(EventTypeError):
    """Exception for when an event schema is not found."""

    def __init__(self, event_type: str) -> None:
        """Initialize with event type."""
        super().__init__(f"No schema registered for event type: {event_type}")
        self.event_type = event_type
