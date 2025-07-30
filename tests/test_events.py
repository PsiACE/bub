"""Simple tests for Bub's event system - Core Patterns and Features.

These tests verify the essential event system capabilities:
1. Core event-driven patterns
2. Multi-cross-bus communication
3. Event visualization and cascade analysis
"""

import time

import pytest

from bub.events import (
    BaseEvent,
    EventSystem,
    publish,
    register_event,
    set_event_system,
    subscribe,
)
from bub.events.types import DomainEventType

# ============================================================================
# SIMPLE TEST EVENT TYPES
# ============================================================================


class MockEventType(DomainEventType):
    """Simple test event types."""

    TEST_ACTION = "test.action"
    TEST_RESPONSE = "test.response"
    TEST_PROCESSED = "test.processed"


@register_event
class MockActionEvent(BaseEvent):
    """Test action event."""

    event_type = MockEventType.TEST_ACTION
    action: str
    value: int


@register_event
class MockResponseEvent(BaseEvent):
    """Test response event."""

    event_type = MockEventType.TEST_RESPONSE
    response: str
    value: int


@register_event
class MockProcessedEvent(BaseEvent):
    """Test processed event."""

    event_type = MockEventType.TEST_PROCESSED
    result: str
    value: int


# ============================================================================
# CORE EVENT-DRIVEN PATTERN TESTS
# ============================================================================


class TestCoreEventPatterns:
    """Test core event-driven patterns."""

    def setup_method(self):
        """Reset event system before each test."""
        set_event_system(EventSystem())

    def test_basic_event_flow(self):
        """Test basic event flow: action → response."""
        events_received = []

        @subscribe(MockEventType.TEST_ACTION)
        def handle_action(event):
            event_data = event.data
            events_received.append(f"action:{event_data['action']}")

            # Auto-generate response
            response = MockResponseEvent(response=f"Processed {event_data['action']}", value=event_data["value"] * 2)
            publish(response)

        @subscribe(MockEventType.TEST_RESPONSE)
        def handle_response(event):
            event_data = event.data
            events_received.append(f"response:{event_data['response']}")

        # Trigger flow
        action = MockActionEvent(action="click", value=5)
        publish(action)

        # Verify flow
        assert len(events_received) == 2
        assert events_received[0] == "action:click"
        assert events_received[1] == "response:Processed click"

    def test_event_cascade(self):
        """Test event cascade: action → response → processed."""
        cascade_events = []

        @subscribe(MockEventType.TEST_ACTION)
        def trigger_cascade(event):
            event_data = event.data
            cascade_events.append(f"1:action:{event_data['action']}")

            # Trigger response
            response = MockResponseEvent(response=f"Handled {event_data['action']}", value=event_data["value"])
            publish(response)

        @subscribe(MockEventType.TEST_RESPONSE)
        def continue_cascade(event):
            event_data = event.data
            cascade_events.append(f"2:response:{event_data['response']}")

            # Trigger processed
            processed = MockProcessedEvent(result=f"Completed {event_data['response']}", value=event_data["value"] + 10)
            publish(processed)

        @subscribe(MockEventType.TEST_PROCESSED)
        def end_cascade(event):
            event_data = event.data
            cascade_events.append(f"3:processed:{event_data['result']}")

        # Start cascade
        action = MockActionEvent(action="submit", value=10)
        publish(action)

        # Verify cascade
        assert len(cascade_events) == 3
        assert cascade_events[0] == "1:action:submit"
        assert cascade_events[1] == "2:response:Handled submit"
        assert cascade_events[2] == "3:processed:Completed Handled submit"

    def test_multiple_subscribers(self):
        """Test multiple subscribers to same event."""
        handler1_events = []
        handler2_events = []

        @subscribe(MockEventType.TEST_ACTION)
        def handler1(event):
            handler1_events.append(event.data["action"])

        @subscribe(MockEventType.TEST_ACTION)
        def handler2(event):
            handler2_events.append(event.data["action"])

        # Publish event
        action = MockActionEvent(action="test", value=1)
        publish(action)

        # Both handlers should receive the event
        assert handler1_events == ["test"]
        assert handler2_events == ["test"]


# ============================================================================
# MULTI-CROSS-BUS COMMUNICATION TESTS
# ============================================================================


class TestMultiBusCommunication:
    """Test multi-cross-bus communication."""

    def setup_method(self):
        """Reset event system before each test."""
        set_event_system(EventSystem())

    def test_cross_bus_event_flow(self):
        """Test events flowing across multiple buses."""
        # Create separate event systems
        bus1 = EventSystem()
        bus2 = EventSystem()

        cross_bus_events = []

        # Bus 1 handler
        @bus1.subscribe(MockEventType.TEST_ACTION)
        def bus1_handler(event):
            event_data = event.data
            cross_bus_events.append(f"bus1:{event_data['action']}")

            # Send to bus 2
            response = MockResponseEvent(response=f"From bus1: {event_data['action']}", value=event_data["value"])
            bus2.publish(response)

        # Bus 2 handler
        @bus2.subscribe(MockEventType.TEST_RESPONSE)
        def bus2_handler(event):
            event_data = event.data
            cross_bus_events.append(f"bus2:{event_data['response']}")

        # Start flow on bus 1
        action = MockActionEvent(action="cross_bus_test", value=5)
        bus1.publish(action)

        # Verify cross-bus flow
        assert len(cross_bus_events) == 2
        assert cross_bus_events[0] == "bus1:cross_bus_test"
        assert cross_bus_events[1] == "bus2:From bus1: cross_bus_test"

    def test_three_bus_cascade(self):
        """Test cascade across three buses."""
        bus1 = EventSystem()
        bus2 = EventSystem()
        bus3 = EventSystem()

        cascade_log = []

        # Bus 1: Action
        @bus1.subscribe(MockEventType.TEST_ACTION)
        def bus1_action(event):
            event_data = event.data
            cascade_log.append(f"bus1:action:{event_data['action']}")

            # Send to bus 2
            response = MockResponseEvent(response=f"Bus1 processed {event_data['action']}", value=event_data["value"])
            bus2.publish(response)

        # Bus 2: Response
        @bus2.subscribe(MockEventType.TEST_RESPONSE)
        def bus2_response(event):
            event_data = event.data
            cascade_log.append(f"bus2:response:{event_data['response']}")

            # Send to bus 3
            processed = MockProcessedEvent(
                result=f"Bus2 completed {event_data['response']}", value=event_data["value"] + 5
            )
            bus3.publish(processed)

        # Bus 3: Processed
        @bus3.subscribe(MockEventType.TEST_PROCESSED)
        def bus3_processed(event):
            event_data = event.data
            cascade_log.append(f"bus3:processed:{event_data['result']}")

        # Start cascade
        action = MockActionEvent(action="three_bus_test", value=10)
        bus1.publish(action)

        # Verify three-bus cascade
        assert len(cascade_log) == 3
        assert cascade_log[0] == "bus1:action:three_bus_test"
        assert cascade_log[1] == "bus2:response:Bus1 processed three_bus_test"
        assert cascade_log[2] == "bus3:processed:Bus2 completed Bus1 processed three_bus_test"


# ============================================================================
# EVENT VISUALIZATION AND CASCADE ANALYSIS TESTS
# ============================================================================


class TestEventVisualization:
    """Test event visualization and analysis capabilities."""

    def setup_method(self):
        """Reset event system before each test."""
        set_event_system(EventSystem())

    def test_event_history_tracking(self):
        """Test tracking event history for visualization."""
        event_history = []

        @subscribe(MockEventType.TEST_ACTION)
        def track_action(event):
            event_data = event.data
            event_history.append({
                "type": "action",
                "action": event_data["action"],
                "value": event_data["value"],
                "timestamp": time.time(),
            })

        @subscribe(MockEventType.TEST_RESPONSE)
        def track_response(event):
            event_data = event.data
            event_history.append({
                "type": "response",
                "response": event_data["response"],
                "value": event_data["value"],
                "timestamp": time.time(),
            })

        # Generate events
        actions = ["login", "search", "logout"]
        for action in actions:
            event = MockActionEvent(action=action, value=len(action))
            publish(event)

            response = MockResponseEvent(response=f"Handled {action}", value=len(action) * 2)
            publish(response)

        # Verify event history
        assert len(event_history) == 6  # 3 actions + 3 responses

        # Check action events
        action_events = [e for e in event_history if e["type"] == "action"]
        assert len(action_events) == 3
        assert action_events[0]["action"] == "login"
        assert action_events[1]["action"] == "search"
        assert action_events[2]["action"] == "logout"

        # Check response events
        response_events = [e for e in event_history if e["type"] == "response"]
        assert len(response_events) == 3
        assert response_events[0]["response"] == "Handled login"

    def test_cascade_analysis(self):
        """Test analyzing event cascades."""
        cascades = []
        current_cascade = []

        @subscribe(MockEventType.TEST_ACTION)
        def start_cascade(event):
            nonlocal current_cascade
            event_data = event.data
            current_cascade = [f"action:{event_data['action']}"]

        @subscribe(MockEventType.TEST_RESPONSE)
        def continue_cascade(event):
            nonlocal current_cascade
            event_data = event.data
            current_cascade.append(f"response:{event_data['response']}")

        @subscribe(MockEventType.TEST_PROCESSED)
        def end_cascade(event):
            nonlocal current_cascade
            event_data = event.data
            current_cascade.append(f"processed:{event_data['result']}")
            cascades.append(current_cascade.copy())

        # Generate cascades
        # Cascade 1: Simple
        action1 = MockActionEvent(action="simple", value=1)
        publish(action1)

        response1 = MockResponseEvent(response="Simple response", value=2)
        publish(response1)

        processed1 = MockProcessedEvent(result="Simple completed", value=3)
        publish(processed1)

        # Cascade 2: Complex
        action2 = MockActionEvent(action="complex", value=10)
        publish(action2)

        response2 = MockResponseEvent(response="Complex response", value=20)
        publish(response2)

        processed2 = MockProcessedEvent(result="Complex completed", value=30)
        publish(processed2)

        # Analyze cascades
        assert len(cascades) == 2

        # Verify cascade 1
        assert len(cascades[0]) == 3
        assert cascades[0][0] == "action:simple"
        assert cascades[0][1] == "response:Simple response"
        assert cascades[0][2] == "processed:Simple completed"

        # Verify cascade 2
        assert len(cascades[1]) == 3
        assert cascades[1][0] == "action:complex"
        assert cascades[1][1] == "response:Complex response"
        assert cascades[1][2] == "processed:Complex completed"

        # Cascade statistics
        avg_length = sum(len(cascade) for cascade in cascades) / len(cascades)
        assert avg_length == 3.0
        assert max(len(cascade) for cascade in cascades) == 3


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestEventSystemIntegration:
    """Test integration of all event system features."""

    def setup_method(self):
        """Reset event system before each test."""
        set_event_system(EventSystem())

    def test_complete_workflow(self):
        """Test a complete workflow using all features."""
        # Track everything
        workflow_log = []
        event_history = []
        cascades = []
        current_cascade = []

        # Event handlers
        @subscribe(MockEventType.TEST_ACTION)
        def handle_action(event):
            event_data = event.data
            workflow_log.append(f"action:{event_data['action']}")
            event_history.append({"type": "action", "action": event_data["action"]})
            current_cascade.append(f"action:{event_data['action']}")

            # Auto-response
            response = MockResponseEvent(response=f"Processed {event_data['action']}", value=event_data["value"] * 2)
            publish(response)

        @subscribe(MockEventType.TEST_RESPONSE)
        def handle_response(event):
            event_data = event.data
            workflow_log.append(f"response:{event_data['response']}")
            event_history.append({"type": "response", "response": event_data["response"]})
            current_cascade.append(f"response:{event_data['response']}")

            # Auto-process
            processed = MockProcessedEvent(result=f"Completed {event_data['response']}", value=event_data["value"] + 5)
            publish(processed)

        @subscribe(MockEventType.TEST_PROCESSED)
        def handle_processed(event):
            event_data = event.data
            workflow_log.append(f"processed:{event_data['result']}")
            event_history.append({"type": "processed", "result": event_data["result"]})
            current_cascade.append(f"processed:{event_data['result']}")
            cascades.append(current_cascade.copy())

        # Execute workflow
        action = MockActionEvent(action="integration_test", value=10)
        publish(action)

        # Verify complete workflow
        assert len(workflow_log) == 3
        assert workflow_log[0] == "action:integration_test"
        assert workflow_log[1] == "response:Processed integration_test"
        assert workflow_log[2] == "processed:Completed Processed integration_test"

        # Verify event history
        assert len(event_history) == 3
        assert event_history[0]["type"] == "action"
        assert event_history[1]["type"] == "response"
        assert event_history[2]["type"] == "processed"

        # Verify cascade
        assert len(cascades) == 1
        assert len(cascades[0]) == 3
        assert cascades[0][0] == "action:integration_test"
        assert cascades[0][1] == "response:Processed integration_test"
        assert cascades[0][2] == "processed:Completed Processed integration_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
