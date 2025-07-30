"""Simple Bub Event System Examples - Core Patterns and Features.

This module demonstrates the essential event system capabilities:
1. Core event-driven patterns
2. Multi-cross-bus communication
3. Event visualization and cascade analysis
4. Simple, user-friendly examples
"""

from __future__ import annotations

import time

from bub.events import (
    BaseEvent,
    EventSystem,
    get_event_system,
    publish,
    register_event,
    subscribe,
)
from bub.events.types import DomainEventType

# ============================================================================
# SIMPLE EVENT TYPES
# ============================================================================


class SimpleEventType(DomainEventType):
    """Simple event types for demonstration."""

    USER_ACTION = "user.action"
    SYSTEM_RESPONSE = "system.response"
    DATA_PROCESSED = "data.processed"
    NOTIFICATION_SENT = "notification.sent"


@register_event
class UserActionEvent(BaseEvent):
    """User performs an action."""

    event_type = SimpleEventType.USER_ACTION
    action: str
    user_id: str
    timestamp: float


@register_event
class SystemResponseEvent(BaseEvent):
    """System responds to user action."""

    event_type = SimpleEventType.SYSTEM_RESPONSE
    response: str
    user_id: str
    timestamp: float


@register_event
class DataProcessedEvent(BaseEvent):
    """Data has been processed."""

    event_type = SimpleEventType.DATA_PROCESSED
    data_type: str
    result: str
    timestamp: float


@register_event
class NotificationSentEvent(BaseEvent):
    """Notification was sent."""

    event_type = SimpleEventType.NOTIFICATION_SENT
    message: str
    recipient: str
    timestamp: float


# ============================================================================
# CORE EVENT-DRIVEN PATTERNS
# ============================================================================


def demonstrate_basic_event_flow():
    """Demonstrate basic event-driven communication."""
    print("\nBasic Event Flow")
    print("=" * 30)

    # Track events
    events_log = []

    @subscribe(SimpleEventType.USER_ACTION)
    def handle_user_action(event):
        # Access event data from eventure Event object
        event_data = event.data
        events_log.append(f"User action: {event_data['action']}")

        # System responds automatically
        response = SystemResponseEvent(
            response=f"Processed: {event_data['action']}", user_id=event_data["user_id"], timestamp=time.time()
        )
        publish(response)

    @subscribe(SimpleEventType.SYSTEM_RESPONSE)
    def handle_system_response(event):
        event_data = event.data
        events_log.append(f"System response: {event_data['response']}")

    # User performs action
    user_action = UserActionEvent(action="click_button", user_id="user123", timestamp=time.time())

    print("User clicks button...")
    publish(user_action)

    # Show event flow
    for event in events_log:
        print(event)

    print("Event-driven flow completed!")


def demonstrate_event_cascade():
    """Demonstrate how events cascade through the system."""
    print("\nEvent Cascade")
    print("=" * 30)

    cascade_log = []

    @subscribe(SimpleEventType.USER_ACTION)
    def trigger_cascade(event):
        event_data = event.data
        cascade_log.append(f"1. User action: {event_data['action']}")

        # Trigger data processing
        data_event = DataProcessedEvent(
            data_type="user_input", result=f"Processed {event_data['action']}", timestamp=time.time()
        )
        publish(data_event)

    @subscribe(SimpleEventType.DATA_PROCESSED)
    def handle_data_processed(event):
        event_data = event.data
        cascade_log.append(f"2. Data processed: {event_data['result']}")

        # Trigger notification
        notification = NotificationSentEvent(
            message=f"Your {event_data['data_type']} was processed", recipient="user123", timestamp=time.time()
        )
        publish(notification)

    @subscribe(SimpleEventType.NOTIFICATION_SENT)
    def handle_notification(event):
        event_data = event.data
        cascade_log.append(f"3. Notification sent: {event_data['message']}")

    # Start the cascade
    print("User performs action...")
    user_action = UserActionEvent(action="submit_form", user_id="user123", timestamp=time.time())
    publish(user_action)

    # Show cascade
    for step in cascade_log:
        print(step)

    print("Event cascade completed!")


# ============================================================================
# MULTI-CROSS-BUS COMMUNICATION
# ============================================================================


def demonstrate_multi_bus_communication():
    """Demonstrate communication across multiple event buses."""
    print("\nMulti-Bus Communication")
    print("=" * 40)

    # Create separate event systems for different domains
    user_system = EventSystem()
    data_system = EventSystem()
    notification_system = EventSystem()

    # Track cross-bus communication
    cross_bus_log = []

    # User bus handlers
    @user_system.subscribe(SimpleEventType.USER_ACTION)
    def handle_user_action(event):
        event_data = event.data
        cross_bus_log.append(f"User bus: {event_data['action']}")

        # Send to data bus
        data_event = DataProcessedEvent(
            data_type="user_action", result=f"Processing {event_data['action']}", timestamp=time.time()
        )
        data_system.publish(data_event)

    # Data bus handlers
    @data_system.subscribe(SimpleEventType.DATA_PROCESSED)
    def handle_data_processed(event):
        event_data = event.data
        cross_bus_log.append(f"Data bus: {event_data['result']}")

        # Send to notification bus
        notification = NotificationSentEvent(
            message=f"Data processed: {event_data['result']}", recipient="user123", timestamp=time.time()
        )
        notification_system.publish(notification)

    # Notification bus handlers
    @notification_system.subscribe(SimpleEventType.NOTIFICATION_SENT)
    def handle_notification(event):
        event_data = event.data
        cross_bus_log.append(f"Notification bus: {event_data['message']}")

    # Start cross-bus flow
    print("Starting cross-bus communication...")
    user_action = UserActionEvent(action="upload_file", user_id="user123", timestamp=time.time())
    user_system.publish(user_action)

    # Show cross-bus flow
    for step in cross_bus_log:
        print(step)

    print("Multi-bus communication completed!")


def demonstrate_single_system_multi_bus():
    """Demonstrate multiple buses within a single event system."""
    print("\nSingle System Multi-Bus Communication")
    print("=" * 45)

    # Create a single event system with multiple buses
    event_system = EventSystem()

    # Create additional buses within the same system
    event_system.create_bus("user")
    event_system.create_bus("data")
    event_system.create_bus("notification")

    # Track multi-bus communication
    multi_bus_log = []

    # Subscribe to events on different buses within the same system
    @event_system.subscribe(SimpleEventType.USER_ACTION, bus="user")
    def handle_user_action(event):
        event_data = event.data
        multi_bus_log.append(f"User bus: {event_data['action']}")

        # Publish to data bus within the same system
        data_event = DataProcessedEvent(
            data_type="user_action", result=f"Processing {event_data['action']}", timestamp=time.time()
        )
        event_system.publish(data_event, bus="data")

    @event_system.subscribe(SimpleEventType.DATA_PROCESSED, bus="data")
    def handle_data_processed(event):
        event_data = event.data
        multi_bus_log.append(f"Data bus: {event_data['result']}")

        # Publish to notification bus within the same system
        notification = NotificationSentEvent(
            message=f"Data processed: {event_data['result']}", recipient="user123", timestamp=time.time()
        )
        event_system.publish(notification, bus="notification")

    @event_system.subscribe(SimpleEventType.NOTIFICATION_SENT, bus="notification")
    def handle_notification(event):
        event_data = event.data
        multi_bus_log.append(f"Notification bus: {event_data['message']}")

    # Start multi-bus flow within single system
    print("Starting single system multi-bus communication...")
    user_action = UserActionEvent(action="process_data", user_id="user123", timestamp=time.time())
    event_system.publish(user_action, bus="user")

    # Show multi-bus flow
    for step in multi_bus_log:
        print(step)

    print("Single system multi-bus communication completed!")

    # Demonstrate bus isolation
    print("\nBus Isolation Test:")
    isolation_log = []

    @event_system.subscribe(SimpleEventType.USER_ACTION, bus="default")
    def handle_default_bus(event):
        isolation_log.append("Default bus handler triggered")

    @event_system.subscribe(SimpleEventType.USER_ACTION, bus="user")
    def handle_user_bus(event):
        isolation_log.append("User bus handler triggered")

    # Publish to user bus only
    event_system.publish(UserActionEvent(action="test", user_id="user123", timestamp=time.time()), bus="user")

    print("Bus isolation results:")
    for log in isolation_log:
        print(f"  - {log}")


# ============================================================================
# EVENT VISUALIZATION AND ANALYSIS
# ============================================================================


def demonstrate_event_visualization():
    """Demonstrate event visualization using native eventure features."""
    print("\nEvent Visualization (Native Eventure)")
    print("=" * 45)

    # Get the event system and its underlying eventure components
    event_system = get_event_system()
    event_query = event_system.get_query()

    # Generate events for visualization using default bus
    print("Generating events for visualization...")

    actions = ["login", "search", "download", "logout"]
    for action in actions:
        # User action events
        user_action = UserActionEvent(action=action, user_id="user123", timestamp=time.time())
        publish(user_action)
        time.sleep(0.1)

        # System response events
        response = SystemResponseEvent(response=f"Processed: {action}", user_id="user123", timestamp=time.time())
        publish(response)
        time.sleep(0.1)

        # Data processed events
        data_event = DataProcessedEvent(data_type="user_input", result=f"Processed {action}", timestamp=time.time())
        publish(data_event)
        time.sleep(0.1)

        # Notification events
        notification = NotificationSentEvent(
            message="Your user_input was processed", recipient="user123", timestamp=time.time()
        )
        publish(notification)
        time.sleep(0.1)

    # Use only native eventure visualization
    print("\nNative Eventure Visualization:")
    print("-" * 50)
    event_query.print_event_cascade()


def demonstrate_cascade_analysis():
    """Demonstrate cascade analysis using native eventure features."""
    print("\nCascade Analysis (Native Eventure)")
    print("=" * 40)

    # Get eventure components
    event_system = get_event_system()
    event_query = event_system.get_query()

    # Generate cascades for analysis
    print("Generating event cascades for analysis...")

    # Cascade 1: Simple action
    user_action = UserActionEvent(action="click_button", user_id="user123", timestamp=time.time())
    publish(user_action)

    response = SystemResponseEvent(response="Button clicked", user_id="user123", timestamp=time.time())
    publish(response)

    notification = NotificationSentEvent(message="Action completed", recipient="user123", timestamp=time.time())
    publish(notification)

    # Cascade 2: Complex action
    user_action2 = UserActionEvent(action="upload_file", user_id="user123", timestamp=time.time())
    publish(user_action2)

    response2 = SystemResponseEvent(response="File received", user_id="user123", timestamp=time.time())
    publish(response2)

    data_processed = DataProcessedEvent(
        data_type="file_upload", result="File processed successfully", timestamp=time.time()
    )
    publish(data_processed)

    notification2 = NotificationSentEvent(
        message="File uploaded and processed", recipient="user123", timestamp=time.time()
    )
    publish(notification2)

    # Use only native eventure cascade analysis
    print("\nNative Eventure Cascade Analysis:")
    print("-" * 50)

    # Get all events and show cascades
    all_events = event_query.get_root_events()
    if all_events:
        # Show cascade for the first event
        event_query.print_single_cascade(all_events[0])

        # Show cascade for a middle event if available
        if len(all_events) > 2:
            print("\nCascade for middle event:")
            event_query.print_single_cascade(all_events[len(all_events) // 2])

        # Show cascade for the last event
        print("\nCascade for last event:")
        event_query.print_single_cascade(all_events[-1])


# ============================================================================
# SIMPLE INTEGRATION EXAMPLE
# ============================================================================


def demonstrate_simple_integration():
    """Demonstrate simple integration of all features."""
    print("\nSimple Integration Example")
    print("=" * 40)

    print("Starting integrated event system demo...")

    # 1. Basic event flow
    demonstrate_basic_event_flow()

    # 2. Event cascade
    demonstrate_event_cascade()

    # 3. Multi-bus communication
    demonstrate_multi_bus_communication()

    # 4. Single system multi-bus communication
    demonstrate_single_system_multi_bus()

    # 5. Event visualization
    demonstrate_event_visualization()

    # 6. Cascade analysis
    demonstrate_cascade_analysis()

    print("\nAll demonstrations completed!")
    print("Event system is working correctly!")


# ============================================================================
# MAIN DEMONSTRATION
# ============================================================================


def run_simple_demo():
    """Run the simple event system demonstration."""
    print("Bub Event System - Simple Examples")
    print("=" * 50)
    print("This demo shows core event-driven patterns and features.")
    print()

    demonstrate_simple_integration()


if __name__ == "__main__":
    run_simple_demo()
