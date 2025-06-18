"""Tests for vextir_os event_bus module"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from lightning_core.vextir_os.event_bus import (
    EventBus,
    EventFilter,
    EventStream,
    EventSubscription,
    emit_event,
    get_event_bus,
    subscribe_to_events,
)
from lightning_core.vextir_os.events import Event, EventCategory


class TestEventFilter:
    """Test EventFilter functionality"""

    def test_empty_filter_matches_all(self):
        """Test that empty filter matches all events"""
        filter = EventFilter()
        event = Event(type="test.event", source="test-source", user_id="user-123")

        assert filter.matches(event) is True

    def test_event_type_filter(self):
        """Test filtering by event type"""
        filter = EventFilter(event_types=["user.click", "user.scroll"])

        matching_event = Event(type="user.click")
        non_matching_event = Event(type="system.startup")

        assert filter.matches(matching_event) is True
        assert filter.matches(non_matching_event) is False

    def test_source_filter(self):
        """Test filtering by event source"""
        filter = EventFilter(sources=["web-ui", "mobile-app"])

        matching_event = Event(type="test.event", source="web-ui")
        non_matching_event = Event(type="test.event", source="api")

        assert filter.matches(matching_event) is True
        assert filter.matches(non_matching_event) is False

    def test_user_id_filter(self):
        """Test filtering by user ID"""
        filter = EventFilter(user_ids=["user-123", "user-456"])

        matching_event = Event(type="test.event", user_id="user-123")
        non_matching_event = Event(type="test.event", user_id="user-789")

        assert filter.matches(matching_event) is True
        assert filter.matches(non_matching_event) is False

    def test_category_filter(self):
        """Test filtering by event category"""
        filter = EventFilter(categories=[EventCategory.INPUT, EventCategory.OUTPUT])

        input_event = Event(type="test.event", category=EventCategory.INPUT)
        output_event = Event(type="test.event", category=EventCategory.OUTPUT)
        internal_event = Event(type="test.event", category=EventCategory.INTERNAL)

        assert filter.matches(input_event) is True
        assert filter.matches(output_event) is True
        assert filter.matches(internal_event) is False

    def test_combined_filters(self):
        """Test combining multiple filter criteria"""
        filter = EventFilter(
            event_types=["user.action"],
            sources=["web-ui"],
            user_ids=["user-123"],
            categories=[EventCategory.INPUT],
        )

        # Event matching all criteria
        matching_event = Event(
            type="user.action",
            source="web-ui",
            user_id="user-123",
            category=EventCategory.INPUT,
        )

        # Events failing different criteria
        wrong_type = Event(
            type="system.event",
            source="web-ui",
            user_id="user-123",
            category=EventCategory.INPUT,
        )

        wrong_source = Event(
            type="user.action",
            source="mobile-app",
            user_id="user-123",
            category=EventCategory.INPUT,
        )

        assert filter.matches(matching_event) is True
        assert filter.matches(wrong_type) is False
        assert filter.matches(wrong_source) is False


class TestEventBus:
    """Test EventBus functionality"""

    @pytest.fixture
    def event_bus(self):
        """Create a fresh event bus for each test"""
        return EventBus()

    @pytest.mark.asyncio
    async def test_emit_event(self, event_bus):
        """Test emitting an event"""
        event = Event(type="test.event", data={"message": "test"})

        event_id = await event_bus.emit(event)

        assert event_id is not None
        assert event.id == event_id

        # Check event is in history
        history = await event_bus.get_history()
        assert len(history) == 1
        assert history[0].id == event_id

    @pytest.mark.asyncio
    async def test_emit_event_auto_id(self, event_bus):
        """Test that events get auto-assigned IDs if not provided"""
        event = Event(type="test.event")
        original_id = event.id

        event_id = await event_bus.emit(event)

        assert event_id == original_id
        assert event.id is not None

    @pytest.mark.asyncio
    async def test_subscribe_callback(self, event_bus):
        """Test subscribing with callback"""
        received_events = []

        def callback(event):
            received_events.append(event)

        filter = EventFilter(event_types=["test.event"])
        subscription_id = event_bus.subscribe(filter, callback)

        # Emit matching event
        matching_event = Event(type="test.event")
        await event_bus.emit(matching_event)

        # Emit non-matching event
        non_matching_event = Event(type="other.event")
        await event_bus.emit(non_matching_event)

        assert len(received_events) == 1
        assert received_events[0].type == "test.event"

        # Test unsubscribe
        event_bus.unsubscribe(subscription_id)

        await event_bus.emit(Event(type="test.event"))
        assert len(received_events) == 1  # Should not increase

    @pytest.mark.asyncio
    async def test_subscribe_callback_error_handling(self, event_bus):
        """Test that callback errors don't break the event bus"""

        def failing_callback(event):
            raise Exception("Callback error")

        filter = EventFilter(event_types=["test.event"])
        event_bus.subscribe(filter, failing_callback)

        # This should not raise an exception
        event = Event(type="test.event")
        await event_bus.emit(event)

        # Event should still be in history
        history = await event_bus.get_history()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_event_history(self, event_bus):
        """Test event history functionality"""
        # Emit multiple events
        events = []
        for i in range(5):
            event = Event(type=f"test.event.{i}", data={"index": i})
            await event_bus.emit(event)
            events.append(event)

        # Get all history
        history = await event_bus.get_history()
        assert len(history) == 5

        # Get limited history
        limited_history = await event_bus.get_history(limit=3)
        assert len(limited_history) == 3

        # Should get the most recent events
        assert limited_history[0].data["index"] == 2  # 3rd most recent
        assert limited_history[2].data["index"] == 4  # most recent

    @pytest.mark.asyncio
    async def test_event_history_with_filter(self, event_bus):
        """Test event history with filtering"""
        # Emit events of different types
        await event_bus.emit(Event(type="user.event", data={"index": 1}))
        await event_bus.emit(Event(type="system.event", data={"index": 2}))
        await event_bus.emit(Event(type="user.event", data={"index": 3}))

        # Filter for user events only
        filter = EventFilter(event_types=["user.event"])
        filtered_history = await event_bus.get_history(filter=filter)

        assert len(filtered_history) == 2
        assert all(event.type == "user.event" for event in filtered_history)

    @pytest.mark.asyncio
    async def test_history_size_limit(self, event_bus):
        """Test that history respects max size limit"""
        # Set a small max history for testing
        event_bus.max_history = 3

        # Emit more events than the limit
        for i in range(5):
            await event_bus.emit(Event(type="test.event", data={"index": i}))

        history = await event_bus.get_history()
        assert len(history) == 3

        # Should contain the most recent events
        indices = [event.data["index"] for event in history]
        assert indices == [2, 3, 4]


class TestEventStream:
    """Test EventStream functionality"""

    @pytest.fixture
    def event_bus(self):
        """Create a fresh event bus for each test"""
        return EventBus()

    @pytest.mark.asyncio
    async def test_event_stream_context_manager(self, event_bus):
        """Test EventStream as context manager"""
        received_events = []

        filter = EventFilter(event_types=["test.event"])

        async with EventStream(filter, event_bus) as stream:
            # Emit an event in background
            asyncio.create_task(
                event_bus.emit(Event(type="test.event", data={"test": True}))
            )

            # Get event from stream
            event = await stream.get_event()
            received_events.append(event)

        assert len(received_events) == 1
        assert received_events[0].type == "test.event"
        assert received_events[0].data["test"] is True

    @pytest.mark.asyncio
    async def test_event_stream_filtering(self, event_bus):
        """Test that EventStream only receives matching events"""
        filter = EventFilter(event_types=["target.event"])

        async with EventStream(filter, event_bus) as stream:
            # Emit non-matching event
            await event_bus.emit(Event(type="other.event"))

            # Emit matching event
            asyncio.create_task(
                event_bus.emit(Event(type="target.event", data={"matched": True}))
            )

            # Should only receive the matching event
            event = await stream.get_event()
            assert event.type == "target.event"
            assert event.data["matched"] is True


class TestGlobalEventBus:
    """Test global event bus functions"""

    @pytest.mark.asyncio
    async def test_get_event_bus_singleton(self):
        """Test that get_event_bus returns the same instance"""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_emit_event_global(self):
        """Test global emit_event function"""
        event = Event(type="global.test")

        event_id = await emit_event(event)

        assert event_id is not None
        assert event.id == event_id

        # Verify it's in the global bus
        bus = get_event_bus()
        history = await bus.get_history()
        assert any(e.id == event_id for e in history)

    def test_subscribe_to_events_global(self):
        """Test global subscribe_to_events function"""
        received_events = []

        def callback(event):
            received_events.append(event)

        filter = EventFilter(event_types=["global.subscription.test"])
        subscription_id = subscribe_to_events(filter, callback)

        assert subscription_id is not None

        # Verify subscription is registered
        bus = get_event_bus()
        assert subscription_id in bus.subscriptions


class TestEventSubscription:
    """Test EventSubscription data class"""

    def test_event_subscription_creation(self):
        """Test creating EventSubscription"""
        filter = EventFilter(event_types=["test.event"])
        callback = Mock()

        subscription = EventSubscription(
            id="sub-123", filter=filter, callback=callback, active=True
        )

        assert subscription.id == "sub-123"
        assert subscription.filter == filter
        assert subscription.callback == callback
        assert subscription.active is True

    def test_event_subscription_defaults(self):
        """Test EventSubscription default values"""
        filter = EventFilter()
        callback = Mock()

        subscription = EventSubscription(id="sub-123", filter=filter, callback=callback)

        assert subscription.active is True  # Default value


class TestConcurrentEventHandling:
    """Test concurrent event handling scenarios"""

    @pytest.fixture
    def event_bus(self):
        """Create a fresh event bus for each test"""
        return EventBus()

    @pytest.mark.asyncio
    async def test_concurrent_event_emission(self, event_bus):
        """Test emitting events concurrently"""

        async def emit_events(start_index, count):
            for i in range(count):
                event = Event(type="concurrent.test", data={"index": start_index + i})
                await event_bus.emit(event)

        # Emit events concurrently from multiple tasks
        tasks = [emit_events(0, 10), emit_events(10, 10), emit_events(20, 10)]

        await asyncio.gather(*tasks)

        # Verify all events were recorded
        history = await event_bus.get_history()
        assert len(history) == 30

        # Verify all indices are present
        indices = {event.data["index"] for event in history}
        assert indices == set(range(30))

    @pytest.mark.asyncio
    async def test_concurrent_subscriptions(self, event_bus):
        """Test multiple concurrent subscriptions"""
        received_events_1 = []
        received_events_2 = []

        def callback_1(event):
            received_events_1.append(event)

        def callback_2(event):
            received_events_2.append(event)

        # Subscribe with different filters
        filter_1 = EventFilter(event_types=["type.a"])
        filter_2 = EventFilter(event_types=["type.b"])

        event_bus.subscribe(filter_1, callback_1)
        event_bus.subscribe(filter_2, callback_2)

        # Emit events of both types
        await event_bus.emit(Event(type="type.a", data={"for": "callback_1"}))
        await event_bus.emit(Event(type="type.b", data={"for": "callback_2"}))
        await event_bus.emit(Event(type="type.a", data={"for": "callback_1_again"}))

        assert len(received_events_1) == 2
        assert len(received_events_2) == 1
        assert all(event.type == "type.a" for event in received_events_1)
        assert all(event.type == "type.b" for event in received_events_2)
