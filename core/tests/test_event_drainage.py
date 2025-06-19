"""
Tests for event drainage and orphaned event handling.
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from lightning_core.abstractions import EventMessage
from lightning_core.abstractions.configuration import RuntimeConfig
from lightning_core.runtime import initialize_runtime


@pytest.mark.asyncio
async def test_orphaned_event_detection():
    """Test that events without subscribers are detected as orphaned."""
    # Initialize runtime with local providers
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        # Start event bus
        await runtime.event_bus.start()
        
        # Publish event with no subscribers
        orphan_event = EventMessage(
            event_type="test.orphaned.event",
            data={"test": "data"}
        )
        await runtime.event_bus.publish(orphan_event)
        
        # Give time for processing
        await asyncio.sleep(0.1)
        
        # Check orphaned events
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 1
        assert orphaned[0].id == orphan_event.id
        assert orphaned[0].event_type == "test.orphaned.event"
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_event_with_subscriber_not_orphaned():
    """Test that events with subscribers are not marked as orphaned."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        # Track handled events
        handled_events = []
        
        async def test_handler(event: EventMessage):
            handled_events.append(event)
        
        # Subscribe to event type
        subscription_id = await runtime.event_bus.subscribe(
            "test.subscribed.event",
            test_handler
        )
        
        # Publish event
        event = EventMessage(
            event_type="test.subscribed.event",
            data={"test": "data"}
        )
        await runtime.event_bus.publish(event)
        
        # Give time for processing
        await asyncio.sleep(0.1)
        
        # Check event was handled
        assert len(handled_events) == 1
        assert handled_events[0].id == event.id
        
        # Check no orphaned events
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
        # Cleanup
        await runtime.event_bus.unsubscribe(subscription_id)
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_wildcard_subscriber_prevents_orphaning():
    """Test that wildcard subscribers prevent events from being orphaned."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        handled_events = []
        
        async def wildcard_handler(event: EventMessage):
            handled_events.append(event)
        
        # Subscribe with wildcard
        subscription_id = await runtime.event_bus.subscribe(
            "test.wildcard.*",
            wildcard_handler
        )
        
        # Publish matching event
        event = EventMessage(
            event_type="test.wildcard.specific",
            data={"test": "data"}
        )
        await runtime.event_bus.publish(event)
        
        await asyncio.sleep(0.1)
        
        # Check event was handled
        assert len(handled_events) == 1
        
        # Check no orphaned events
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
        await runtime.event_bus.unsubscribe(subscription_id)
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_event_ttl_expiration():
    """Test that events expire based on TTL."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        # Publish event with short TTL
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
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_drain_orphaned_events():
    """Test draining orphaned events."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        # Publish multiple orphaned events
        events = []
        for i in range(5):
            event = EventMessage(
                event_type=f"test.orphan.type{i % 2}",  # Two different types
                data={"index": i}
            )
            events.append(event)
            await runtime.event_bus.publish(event)
        
        await asyncio.sleep(0.1)
        
        # Check all are orphaned
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 5
        
        # Drain only type0 events
        drained = await runtime.event_bus.drain_orphaned_events(
            event_types=["test.orphan.type0"]
        )
        assert drained == 3  # indices 0, 2, 4
        
        # Check remaining orphaned
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 2
        assert all(e.event_type == "test.orphan.type1" for e in orphaned)
        
        # Drain all remaining
        drained = await runtime.event_bus.drain_orphaned_events()
        assert drained == 2
        
        # Check none remaining
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 0
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_drain_orphaned_events_by_age():
    """Test draining orphaned events by age."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        # Create old event (simulate by modifying timestamp)
        old_event = EventMessage(
            event_type="test.old.orphan",
            data={"age": "old"}
        )
        old_event.timestamp = datetime.utcnow() - timedelta(hours=2)
        
        # Create new event
        new_event = EventMessage(
            event_type="test.new.orphan",
            data={"age": "new"}
        )
        
        # Publish both
        await runtime.event_bus.publish(old_event)
        await runtime.event_bus.publish(new_event)
        
        await asyncio.sleep(0.1)
        
        # Check both are orphaned
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 2
        
        # Drain events older than 1 hour
        before = datetime.utcnow() - timedelta(hours=1)
        drained = await runtime.event_bus.drain_orphaned_events(before=before)
        assert drained == 1
        
        # Check only new event remains
        orphaned = await runtime.event_bus.get_orphaned_events()
        assert len(orphaned) == 1
        assert orphaned[0].id == new_event.id
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_has_subscribers_method():
    """Test checking if event type has subscribers."""
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        # Initially no subscribers
        assert not await runtime.event_bus.has_subscribers("test.event")
        
        # Add subscriber
        async def handler(event: EventMessage):
            pass
        
        subscription_id = await runtime.event_bus.subscribe("test.event", handler)
        
        # Now has subscribers
        assert await runtime.event_bus.has_subscribers("test.event")
        
        # Test wildcard matching
        assert await runtime.event_bus.has_subscribers("test.event.specific")  # Should not match
        
        # Add wildcard subscriber
        wildcard_id = await runtime.event_bus.subscribe("test.*", handler)
        assert await runtime.event_bus.has_subscribers("test.anything")
        
        # Cleanup
        await runtime.event_bus.unsubscribe(subscription_id)
        await runtime.event_bus.unsubscribe(wildcard_id)
        
        # No subscribers again
        assert not await runtime.event_bus.has_subscribers("test.event")
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio 
async def test_universal_processor_drains_orphaned_events():
    """Test that universal processor automatically drains events with no consumers."""
    from lightning_core.vextir_os.universal_processor import get_universal_processor
    from lightning_core.vextir_os.events import Event
    
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        processor = get_universal_processor()
        
        # Create event with no registered drivers or subscribers
        event = Event(
            id="test-123",
            timestamp=datetime.utcnow(),
            source="test",
            type="nonexistent.event.type",
            user_id="test-user",
            metadata={"test": "data"}
        )
        
        # Process event
        output_events = await processor.process_event(event)
        
        # Should return empty list (drained)
        assert output_events == []
        
        # Check metrics
        metrics = await processor.get_metrics()
        assert metrics["total_orphaned"] == 1
        assert "nonexistent.event.type" in metrics["orphaned_types"]
        
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_event_monitoring():
    """Test event monitoring functionality."""
    from lightning_core.vextir_os.event_monitoring import get_event_monitor
    
    config = RuntimeConfig(mode="local")
    runtime = await initialize_runtime(config)
    
    try:
        await runtime.event_bus.start()
        
        monitor = get_event_monitor()
        
        # Publish some orphaned events
        for i in range(3):
            event = EventMessage(
                event_type="test.orphan.monitor",
                data={"index": i}
            )
            await runtime.event_bus.publish(event)
        
        await asyncio.sleep(0.1)
        
        # Get health status
        health = await monitor.get_health_status()
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert health["orphaned_event_count"] >= 3
        
        # Get orphaned event summary
        summary = await monitor.get_orphaned_event_summary()
        assert summary["total_count"] >= 3
        assert "test.orphan.monitor" in summary["by_event_type"]
        
        # Cleanup orphaned events
        cleanup_result = await monitor.cleanup_orphaned_events(
            event_types=["test.orphan.monitor"]
        )
        assert cleanup_result["drained_count"] >= 3
        
    finally:
        await runtime.shutdown()


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_orphaned_event_detection())
    asyncio.run(test_event_with_subscriber_not_orphaned())
    asyncio.run(test_wildcard_subscriber_prevents_orphaning())
    asyncio.run(test_event_ttl_expiration())
    asyncio.run(test_drain_orphaned_events())
    asyncio.run(test_drain_orphaned_events_by_age())
    asyncio.run(test_has_subscribers_method())
    asyncio.run(test_universal_processor_drains_orphaned_events())
    asyncio.run(test_event_monitoring())
    
    print("All tests passed!")