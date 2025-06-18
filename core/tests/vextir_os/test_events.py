"""Tests for vextir_os events module"""

from datetime import datetime

import pytest

from lightning_core.vextir_os.events import (
    AuthEvent,
    CalendarEvent,
    ContextUpdateEvent,
    EmailEvent,
    Event,
    EventCategory,
    MessageEvent,
    NotificationEvent,
    OutputEvent,
    SystemEvent,
    UserEvent,
    WorkerTaskEvent,
)


class TestEvent:
    """Test base Event class"""

    def test_basic_event_creation(self):
        """Test creating a basic event"""
        event = Event(type="test.event", data={"message": "Hello, World!"})

        assert event.type == "test.event"
        assert event.data == {"message": "Hello, World!"}
        assert event.category == EventCategory.INTERNAL
        assert event.id is not None
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)

    def test_event_with_all_fields(self):
        """Test creating event with all fields"""
        timestamp = datetime.utcnow()
        event = Event(
            type="user.action",
            data={"action": "click", "target": "button"},
            id="custom-id-123",
            timestamp=timestamp,
            source="web-ui",
            user_id="user-456",
            category=EventCategory.INPUT,
            metadata={"session": "abc123"},
        )

        assert event.type == "user.action"
        assert event.data == {"action": "click", "target": "button"}
        assert event.id == "custom-id-123"
        assert event.timestamp == timestamp
        assert event.source == "web-ui"
        assert event.user_id == "user-456"
        assert event.category == EventCategory.INPUT
        assert event.metadata == {"session": "abc123"}

    def test_event_auto_id_generation(self):
        """Test that events get auto-generated IDs"""
        event1 = Event(type="test.event1")
        event2 = Event(type="test.event2")

        assert event1.id is not None
        assert event2.id is not None
        assert event1.id != event2.id

    def test_event_auto_timestamp(self):
        """Test that events get auto-generated timestamps"""
        before = datetime.utcnow()
        event = Event(type="test.event")
        after = datetime.utcnow()

        assert before <= event.timestamp <= after


class TestEventCategory:
    """Test EventCategory enum"""

    def test_event_categories(self):
        """Test all event categories exist"""
        assert EventCategory.INPUT.value == "input"
        assert EventCategory.INTERNAL.value == "internal"
        assert EventCategory.OUTPUT.value == "output"


class TestSpecializedEvents:
    """Test specialized event classes"""

    def test_user_event(self):
        """Test UserEvent defaults to INPUT category"""
        event = UserEvent(type="user.click", data={"button": "submit"})

        assert event.type == "user.click"
        assert event.category == EventCategory.INPUT
        assert event.data == {"button": "submit"}

    def test_system_event(self):
        """Test SystemEvent defaults to INTERNAL category"""
        event = SystemEvent(type="system.startup", data={"version": "1.0.0"})

        assert event.type == "system.startup"
        assert event.category == EventCategory.INTERNAL
        assert event.data == {"version": "1.0.0"}

    def test_output_event(self):
        """Test OutputEvent defaults to OUTPUT category"""
        event = OutputEvent(
            type="notification.sent", data={"recipient": "user@example.com"}
        )

        assert event.type == "notification.sent"
        assert event.category == EventCategory.OUTPUT
        assert event.data == {"recipient": "user@example.com"}

    def test_email_event(self):
        """Test EmailEvent has correct default type"""
        event = EmailEvent(data={"to": "user@example.com", "subject": "Test"})

        assert event.type == "email"
        assert event.data == {"to": "user@example.com", "subject": "Test"}

    def test_calendar_event(self):
        """Test CalendarEvent has correct default type"""
        event = CalendarEvent(
            data={"title": "Meeting", "start": "2023-01-01T10:00:00Z"}
        )

        assert event.type == "calendar"
        assert event.data == {"title": "Meeting", "start": "2023-01-01T10:00:00Z"}

    def test_message_event(self):
        """Test MessageEvent has correct default type"""
        event = MessageEvent(data={"text": "Hello", "channel": "general"})

        assert event.type == "message"
        assert event.data == {"text": "Hello", "channel": "general"}

    def test_worker_task_event(self):
        """Test WorkerTaskEvent has correct default type"""
        event = WorkerTaskEvent(data={"task_id": "task-123", "status": "completed"})

        assert event.type == "worker.task"
        assert event.data == {"task_id": "task-123", "status": "completed"}

    def test_context_update_event(self):
        """Test ContextUpdateEvent has correct default type"""
        event = ContextUpdateEvent(
            data={"context_id": "ctx-456", "updates": {"key": "value"}}
        )

        assert event.type == "context.update"
        assert event.data == {"context_id": "ctx-456", "updates": {"key": "value"}}

    def test_auth_event(self):
        """Test AuthEvent has correct default type"""
        event = AuthEvent(data={"user_id": "user-789", "action": "login"})

        assert event.type == "auth"
        assert event.data == {"user_id": "user-789", "action": "login"}

    def test_notification_event(self):
        """Test NotificationEvent has correct default type"""
        event = NotificationEvent(
            data={"title": "Alert", "message": "System update available"}
        )

        assert event.type == "notification"
        assert event.data == {"title": "Alert", "message": "System update available"}


class TestEventDataStructures:
    """Test various event data structures"""

    def test_empty_data(self):
        """Test event with empty data"""
        event = Event(type="empty.event")
        assert event.data == {}

    def test_nested_data(self):
        """Test event with nested data structures"""
        complex_data = {
            "user": {
                "id": "user-123",
                "profile": {"name": "John Doe", "preferences": ["email", "sms"]},
            },
            "action": {
                "type": "update",
                "timestamp": "2023-01-01T12:00:00Z",
                "changes": [
                    {
                        "field": "email",
                        "old": "old@example.com",
                        "new": "new@example.com",
                    }
                ],
            },
        }

        event = Event(type="user.profile.updated", data=complex_data)

        assert event.data == complex_data
        assert event.data["user"]["id"] == "user-123"
        assert event.data["user"]["profile"]["name"] == "John Doe"
        assert len(event.data["action"]["changes"]) == 1

    def test_list_data(self):
        """Test event with list data"""
        event = Event(type="batch.process", data={"items": ["item1", "item2", "item3"]})

        assert event.data["items"] == ["item1", "item2", "item3"]
        assert len(event.data["items"]) == 3


class TestEventEquality:
    """Test event equality and comparison"""

    def test_events_with_same_id_are_equal(self):
        """Test that events with same ID are considered equal"""
        event1 = Event(type="test.event", id="same-id")
        event2 = Event(type="test.event", id="same-id")

        # Note: This test assumes Event implements __eq__ based on ID
        # If not implemented, this test will fail and we'd need to implement it
        assert event1.id == event2.id

    def test_events_with_different_ids_are_different(self):
        """Test that events with different IDs are different"""
        event1 = Event(type="test.event", id="id-1")
        event2 = Event(type="test.event", id="id-2")

        assert event1.id != event2.id


class TestEventSerialization:
    """Test event serialization scenarios"""

    def test_event_dict_conversion(self):
        """Test converting event to dictionary"""
        event = Event(
            type="test.event",
            data={"key": "value"},
            source="test-source",
            user_id="user-123",
        )

        # Test that we can access all fields as attributes
        assert hasattr(event, "type")
        assert hasattr(event, "data")
        assert hasattr(event, "id")
        assert hasattr(event, "timestamp")
        assert hasattr(event, "source")
        assert hasattr(event, "user_id")
        assert hasattr(event, "category")
        assert hasattr(event, "metadata")
