# Event System Architecture

A clean, adapter-based event system that supports both string and Enum event types, with native eventure integration for powerful event visualization and analysis.

## 1. Quick Start

```python
from bub.events import BaseEvent, DomainEventType, register_event, publish, subscribe

# Define event types
class UserEventType(DomainEventType):
    CREATED = "user.created"
    UPDATED = "user.updated"

# Create events
@register_event
class UserCreatedEvent(BaseEvent):
    event_type = UserEventType.CREATED
    user_id: str
    username: str

# Publish and subscribe
@subscribe(UserEventType.CREATED)
def handle_user_created(event):
    print(f"User created: {event.data['username']}")

publish(UserCreatedEvent(user_id="123", username="john"))
```

## 2. Architecture

The event system is built with a clean, modular architecture:

```
src/bub/events/
├── __init__.py          # Main public API
├── types.py             # Type definitions (EventType, DomainEventType)
├── models.py            # Event model definitions (BaseEvent)
├── registry.py          # Schema registry and management
├── adapters.py          # Adapter interfaces
├── system.py            # Main EventSystem facade
├── exceptions.py        # Exception hierarchy
└── backends/
    ├── __init__.py      # Backend exports
    └── eventure.py      # Eventure backend implementation
```

## 3. Core Features

- **Flexible Event Types**: Support for both `str` and `Enum` event types
- **Type Safety**: Full type hints with `EventType = str | Enum`
- **Clean Architecture**: Adapter pattern for pluggable backends
- **Global Singleton**: Convenient global event system
- **Schema Registry**: Automatic event schema registration
- **Native Eventure**: Built-in visualization and cascade analysis
- **Multi-Bus Support**: Cross-bus event communication

## 4. Design Patterns

### 4.1 Event Type Flexibility

The system supports both string and Enum event types seamlessly:

```python
from bub.events.types import DomainEventType, EventType
from enum import Enum

# String-based event types
class StringEvents:
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"

# Enum-based event types
class UserEventType(DomainEventType):
    CREATED = "user.created"
    UPDATED = "user.updated"

# Both work the same way
event_type1: EventType = StringEvents.USER_CREATED
event_type2: EventType = UserEventType.CREATED
```

### 4.2 Event Model Definition

Events are defined as Pydantic models with automatic schema registration:

```python
from bub.events import BaseEvent, register_event

@register_event
class UserCreatedEvent(BaseEvent):
    event_type = UserEventType.CREATED
    user_id: str
    username: str
    email: str

@register_event
class UserUpdatedEvent(BaseEvent):
    event_type = UserEventType.UPDATED
    user_id: str
    changes: dict[str, str]
```

### 4.3 Event-Driven Flow Patterns

#### 4.3.1 Basic Event Flow

```python
from bub.events import publish, subscribe

# Define event types
class MockEventType(DomainEventType):
    TEST_ACTION = "test.action"
    TEST_RESPONSE = "test.response"

@register_event
class MockActionEvent(BaseEvent):
    event_type = MockEventType.TEST_ACTION
    action: str
    value: int

@register_event
class MockResponseEvent(BaseEvent):
    event_type = MockEventType.TEST_RESPONSE
    response: str
    value: int

# Event handlers
@subscribe(MockEventType.TEST_ACTION)
def handle_action(event):
    event_data = event.data
    print(f"Processing action: {event_data['action']}")

    # Auto-generate response
    response = MockResponseEvent(
        response=f"Processed {event_data['action']}",
        value=event_data['value'] * 2
    )
    publish(response)

@subscribe(MockEventType.TEST_RESPONSE)
def handle_response(event):
    event_data = event.data
    print(f"Response: {event_data['response']}")

# Trigger the flow
action = MockActionEvent(action="click", value=5)
publish(action)
# Output:
# Processing action: click
# Response: Processed click
```

#### 4.3.2 Event Cascade Pattern

```python
@subscribe(MockEventType.TEST_ACTION)
def trigger_cascade(event):
    event_data = event.data
    print(f"1. Action: {event_data['action']}")

    # Trigger response
    response = MockResponseEvent(
        response=f"Handled {event_data['action']}",
        value=event_data['value']
    )
    publish(response)

@subscribe(MockEventType.TEST_RESPONSE)
def continue_cascade(event):
    event_data = event.data
    print(f"2. Response: {event_data['response']}")

    # Trigger processed
    processed = MockProcessedEvent(
        result=f"Completed {event_data['response']}",
        value=event_data['value'] + 10
    )
    publish(processed)

@subscribe(MockEventType.TEST_PROCESSED)
def end_cascade(event):
    event_data = event.data
    print(f"3. Processed: {event_data['result']}")

# Start cascade
action = MockActionEvent(action="submit", value=10)
publish(action)
# Output:
# 1. Action: submit
# 2. Response: Handled submit
# 3. Processed: Completed Handled submit
```

### 4.4 Multi-Bus Communication

The system supports communication across multiple event buses:

```python
from bub.events import EventSystem

# Create separate event systems for different domains
user_system = EventSystem()
data_system = EventSystem()
notification_system = EventSystem()

cross_bus_events = []

# User bus handler
@user_system.subscribe(MockEventType.TEST_ACTION)
def user_handler(event):
    event_data = event.data
    cross_bus_events.append(f"User bus: {event_data['action']}")

    # Send to data bus
    response = MockResponseEvent(
        response=f"From user: {event_data['action']}",
        value=event_data['value']
    )
    data_system.publish(response)

# Data bus handler
@data_system.subscribe(MockEventType.TEST_RESPONSE)
def data_handler(event):
    event_data = event.data
    cross_bus_events.append(f"Data bus: {event_data['response']}")

# Start cross-bus flow
action = MockActionEvent(action="upload_file", value=5)
user_system.publish(action)

print(cross_bus_events)
# Output: ['User bus: upload_file', 'Data bus: From user: upload_file']
```

### 4.5 Event Visualization and Analysis

The system provides native eventure integration for powerful event analysis:

```python
from bub.events import get_event_system

# Get the event system and query interface
event_system = get_event_system()
event_query = event_system.get_query()

# Generate some events
for action in ["login", "search", "logout"]:
    event = MockActionEvent(action=action, value=len(action))
    publish(event)

# Use native eventure visualization
print("Event Cascade Visualization:")
event_query.print_event_cascade()

# Analyze specific cascades
all_events = event_query.get_root_events()
if all_events:
    print(f"\nCascade for first event:")
    event_query.print_single_cascade(all_events[0])
```

## 5. API Reference

### 5.1 Core Classes

| Class | Purpose |
|-------|---------|
| `EventSystem` | Main facade for event operations |
| `BaseEvent` | Base class for all events |
| `DomainEventType` | Base for domain event types |
| `EventBusAdapter` | Abstract adapter interface |

### 5.2 Type Definitions

| Type | Description |
|------|-------------|
| `EventType` | `Union[str, Enum]` - Flexible event type support |
| `EventHandler` | `Callable[[Event], None]` - Event handler function |
| `Subscription` | `Callable[[], None]` - Subscription object |

### 5.3 Global Functions

| Function | Purpose |
|----------|---------|
| `publish(event, bus="default")` | Publish event using global system |
| `subscribe(event_type)` | Subscribe to event type using global system |
| `get_event_system()` | Get global event system instance |
| `get_bus()` | Get event bus instance |
| `get_log()` | Get event log instance |
| `get_query()` | Get query interface for analysis |

### 5.4 Registration Functions

| Function | Purpose |
|----------|---------|
| `@register_event` | Decorator for registering event schemas |
| `get_event_schema(event_type)` | Get schema for event type |
| `get_event_schema_or_raise(event_type)` | Get schema or raise exception |

## 6. Best Practices

### 6.1 Event Type Design

```python
# Good: Use domain.action pattern
class UserEventType(DomainEventType):
    CREATED = "user.created"
    UPDATED = "user.updated"
    DELETED = "user.deleted"

# Avoid: Inconsistent naming
class BadEvents:
    USER_CREATED = "user_created"  # Use dots, not underscores
    UPDATE_USER = "update_user"    # Use domain.action pattern
```

### 6.2 Event Data Access

```python
# Correct: Access data from eventure Event objects
@subscribe(UserEventType.CREATED)
def handle_user_created(event):
    event_data = event.data
    user_id = event_data['user_id']
    username = event_data['username']

# Wrong: Direct attribute access
@subscribe(UserEventType.CREATED)
def handle_user_created(event):
    user_id = event.user_id  # This won't work!
```

### 6.3 Event Cascade Design

```python
# Good: Clear cascade flow
@subscribe(UserEventType.CREATED)
def handle_user_created(event):
    # Process user creation
    publish(UserProfileCreatedEvent(user_id=event.data['user_id']))

@subscribe(UserProfileEventType.CREATED)
def handle_profile_created(event):
    # Send welcome notification
    publish(NotificationSentEvent(user_id=event.data['user_id']))

# Avoid: Complex nested cascades
@subscribe(UserEventType.CREATED)
def handle_user_created(event):
    # Don't create multiple cascades in one handler
    publish(Event1())
    publish(Event2())
    publish(Event3())
```

### 6.4 Testing

```python
from bub.events import EventSystem, set_event_system

class TestEventSystem:
    def setup_method(self):
        """Reset event system before each test."""
        set_event_system(EventSystem())

    def test_event_flow(self):
        events_received = []

        @subscribe(MockEventType.TEST_ACTION)
        def handle_action(event):
            events_received.append(event.data['action'])

        publish(MockActionEvent(action="test", value=1))
        assert events_received == ["test"]
```

## 7. Advanced Features

### 7.1 Custom Adapters

```python
from bub.events.adapters import EventBusAdapter

class CustomAdapter(EventBusAdapter):
    def publish(self, event, parent_event=None, bus_name=None):
        # Custom implementation
        print(f"Custom publish: {event.type}")
        return event

    def subscribe(self, event_type, handler, bus_name=None):
        # Custom subscription logic
        print(f"Custom subscribe: {event_type}")
        return lambda: None  # Return unsubscribe function
```

### 7.2 Event Type Normalization

```python
from bub.events.types import normalize_event_type

# All these normalize to the same string:
normalize_event_type("user.created")           # "user.created"
normalize_event_type(UserEventType.CREATED)    # "user.created"
normalize_event_type(StringEvents.USER_CREATED) # "user.created"
```

### 7.3 Domain Event Utilities

```python
@register_event
class UserCreatedEvent(BaseEvent):
    event_type = UserEventType.CREATED  # "user.created"

event = UserCreatedEvent(user_id="123")
print(event.get_domain())   # "user"
print(event.get_action())   # "created"
```

The Event System provides a powerful, flexible foundation for building event-driven applications with clean architecture and excellent developer experience.
