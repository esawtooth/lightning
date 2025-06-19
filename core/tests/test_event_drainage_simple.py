"""
Simplified tests for event drainage and orphaned event handling.
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from lightning_core.abstractions.event_bus import EventMessage
from lightning_core.providers.local.event_bus import LocalEventBus


@pytest.mark.asyncio
async def test_orphaned_event_detection():
    """Test that events without subscribers are detected as orphaned."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        # Publish event with no subscribers
        orphan_event = EventMessage(
            event_type="test.orphaned.event",
            data={"test": "data"}
        )
        await event_bus.publish(orphan_event)
        
        # Give time for processing
        await asyncio.sleep(0.1)
        
        # Check orphaned events
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 1
        assert orphaned[0].id == orphan_event.id
        assert orphaned[0].event_type == "test.orphaned.event"
        
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_event_with_subscriber_not_orphaned():
    """Test that events with subscribers are not marked as orphaned."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        # Track handled events
        handled_events = []
        
        async def test_handler(event: EventMessage):
            handled_events.append(event)
        
        # Subscribe to event type
        subscription_id = await event_bus.subscribe(
            "test.subscribed.event",
            test_handler
        )
        
        # Publish event
        event = EventMessage(
            event_type="test.subscribed.event",
            data={"test": "data"}
        )
        await event_bus.publish(event)
        
        # Give time for processing
        await asyncio.sleep(0.1)
        
        # Check event was handled
        assert len(handled_events) == 1
        assert handled_events[0].id == event.id
        
        # Check no orphaned events
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
        # Cleanup
        await event_bus.unsubscribe(subscription_id)
        
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_wildcard_subscriber_prevents_orphaning():
    """Test that wildcard subscribers prevent events from being orphaned."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        handled_events = []
        
        async def wildcard_handler(event: EventMessage):
            handled_events.append(event)
        
        # Subscribe with wildcard
        subscription_id = await event_bus.subscribe(
            "test.wildcard.*",
            wildcard_handler
        )
        
        # Publish matching event
        event = EventMessage(
            event_type="test.wildcard.specific",
            data={"test": "data"}
        )
        await event_bus.publish(event)
        
        await asyncio.sleep(0.1)
        
        # Check event was handled
        assert len(handled_events) == 1
        
        # Check no orphaned events
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
        await event_bus.unsubscribe(subscription_id)
        
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_event_ttl_expiration():
    """Test that events expire based on TTL."""
    event_bus = LocalEventBus(default_ttl_seconds=60)
    
    # Create event with short TTL
    event = EventMessage(
        event_type="test.ttl.event",
        data={"test": "data"},
        ttl_seconds=1  # 1 second TTL
    )
    
    # Check not expired initially
    assert not event.is_expired()
    
    # Wait for expiration
    await asyncio.sleep(1.5)
    
    # Check expired
    assert event.is_expired()


@pytest.mark.asyncio
async def test_drain_orphaned_events():
    """Test draining orphaned events."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        # Publish multiple orphaned events
        events = []
        for i in range(5):
            event = EventMessage(
                event_type=f"test.orphan.type{i % 2}",  # Two different types
                data={"index": i}
            )
            events.append(event)
            await event_bus.publish(event)
        
        await asyncio.sleep(0.1)
        
        # Check all are orphaned
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 5
        
        # Drain only type0 events
        drained = await event_bus.drain_orphaned_events(
            event_types=["test.orphan.type0"]
        )
        assert drained == 3  # indices 0, 2, 4
        
        # Check remaining orphaned
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 2
        assert all(e.event_type == "test.orphan.type1" for e in orphaned)
        
        # Drain all remaining
        drained = await event_bus.drain_orphaned_events()
        assert drained == 2
        
        # Check none remaining
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_has_subscribers_method():
    """Test checking if event type has subscribers."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        # Initially no subscribers
        assert not await event_bus.has_subscribers("test.event")
        
        # Add subscriber
        async def handler(event: EventMessage):
            pass
        
        subscription_id = await event_bus.subscribe("test.event", handler)
        
        # Now has subscribers
        assert await event_bus.has_subscribers("test.event")
        
        # Test wildcard matching
        assert not await event_bus.has_subscribers("test.event.specific")  # Should not match exact
        
        # Add wildcard subscriber
        wildcard_id = await event_bus.subscribe("test.*", handler)
        assert await event_bus.has_subscribers("test.anything")
        
        # Cleanup
        await event_bus.unsubscribe(subscription_id)
        await event_bus.unsubscribe(wildcard_id)
        
        # No subscribers again
        assert not await event_bus.has_subscribers("test.event")
        
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_expired_events_are_dropped():
    """Test that expired events are automatically dropped during processing."""
    event_bus = LocalEventBus()
    await event_bus.start()
    
    try:
        handled_events = []
        
        async def handler(event: EventMessage):
            handled_events.append(event)
        
        # Subscribe to all events
        await event_bus.subscribe("*", handler)
        
        # Create already expired event
        expired_event = EventMessage(
            event_type="test.expired",
            data={"test": "data"},
            ttl_seconds=1
        )
        # Simulate age by modifying timestamp
        expired_event.timestamp = datetime.utcnow() - timedelta(seconds=2)
        
        # Publish expired event
        await event_bus.publish(expired_event)
        
        await asyncio.sleep(0.1)
        
        # Event should not be handled
        assert len(handled_events) == 0
        
        # Should not be in orphaned events either
        orphaned = await event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
    finally:
        await event_bus.stop()


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_orphaned_event_detection())
    asyncio.run(test_event_with_subscriber_not_orphaned())
    asyncio.run(test_wildcard_subscriber_prevents_orphaning())
    asyncio.run(test_event_ttl_expiration())
    asyncio.run(test_drain_orphaned_events())
    asyncio.run(test_has_subscribers_method())
    asyncio.run(test_expired_events_are_dropped())
    
    print("All tests passed!")