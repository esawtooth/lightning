"""
Tests for event deduplication and replay functionality.
"""

import asyncio
import json
from datetime import datetime, timedelta
import pytest

from lightning_core.abstractions.event_bus import (
    EventMessage,
    EventPriority,
    DeduplicationConfig,
    ReplayConfig,
)
from lightning_core.providers.local.event_bus import LocalEventBus


@pytest.mark.asyncio
async def test_event_deduplication():
    """Test that duplicate events are properly deduplicated."""
    # Create event bus with deduplication enabled
    dedup_config = DeduplicationConfig(
        enabled=True,
        window_seconds=60,
        max_cache_size=100
    )
    bus = LocalEventBus(dedup_config=dedup_config)
    
    await bus.start()
    
    # Track received events
    received_events = []
    
    async def handler(event: EventMessage):
        received_events.append(event)
    
    # Subscribe to events
    await bus.subscribe("test.event", handler)
    
    # Create identical events
    event1 = EventMessage(
        event_type="test.event",
        data={"value": 42, "message": "test"},
        metadata={"source": "test"}
    )
    
    event2 = EventMessage(
        event_type="test.event",
        data={"value": 42, "message": "test"},
        metadata={"source": "test"}
    )
    
    # Publish both events
    await bus.publish(event1)
    await bus.publish(event2)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Should only receive one event
    assert len(received_events) == 1
    assert received_events[0].id == event1.id
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_deduplication_with_idempotency_key():
    """Test deduplication using explicit idempotency keys."""
    dedup_config = DeduplicationConfig(enabled=True)
    bus = LocalEventBus(dedup_config=dedup_config)
    
    await bus.start()
    
    received_events = []
    
    async def handler(event: EventMessage):
        received_events.append(event)
    
    await bus.subscribe("test.event", handler)
    
    # Create events with same idempotency key
    event1 = EventMessage(
        event_type="test.event",
        data={"value": 1},
        idempotency_key="unique-operation-123"
    )
    
    event2 = EventMessage(
        event_type="test.event",
        data={"value": 2},  # Different data
        idempotency_key="unique-operation-123"  # Same key
    )
    
    await bus.publish(event1)
    await bus.publish(event2)
    
    await asyncio.sleep(0.1)
    
    # Should only receive first event
    assert len(received_events) == 1
    assert received_events[0].data["value"] == 1
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_deduplication_window():
    """Test that deduplication window is respected."""
    dedup_config = DeduplicationConfig(
        enabled=True,
        window_seconds=1  # 1 second window
    )
    bus = LocalEventBus(dedup_config=dedup_config)
    
    await bus.start()
    
    received_events = []
    
    async def handler(event: EventMessage):
        received_events.append(event)
    
    await bus.subscribe("test.event", handler)
    
    # Create identical events
    event_data = {"value": 42}
    
    # First event
    event1 = EventMessage(event_type="test.event", data=event_data)
    await bus.publish(event1)
    
    # Wait for window to expire
    await asyncio.sleep(1.5)
    
    # Second identical event after window
    event2 = EventMessage(event_type="test.event", data=event_data)
    await bus.publish(event2)
    
    await asyncio.sleep(0.1)
    
    # Should receive both events
    assert len(received_events) == 2
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_replay():
    """Test event replay functionality."""
    replay_config = ReplayConfig(
        enabled=True,
        max_history_size=1000,
        retention_seconds=3600
    )
    bus = LocalEventBus(replay_config=replay_config)
    
    await bus.start()
    
    # Publish some events
    start_time = datetime.utcnow()
    
    for i in range(10):
        event = EventMessage(
            event_type=f"test.event.{i % 3}",
            data={"index": i},
            correlation_id="test-correlation" if i % 2 == 0 else None
        )
        await bus.publish(event)
        await asyncio.sleep(0.01)
    
    mid_time = datetime.utcnow()
    
    for i in range(10, 20):
        event = EventMessage(
            event_type=f"test.event.{i % 3}",
            data={"index": i}
        )
        await bus.publish(event)
        await asyncio.sleep(0.01)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Test replay by time range
    replayed = await bus.replay_events(start_time, mid_time)
    assert len(replayed) == 10
    assert all(e.data["index"] < 10 for e in replayed)
    
    # Test replay by event type
    replayed = await bus.replay_events(
        start_time,
        event_types=["test.event.0"]
    )
    assert all(e.event_type == "test.event.0" for e in replayed)
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_history_by_correlation_id():
    """Test retrieving event history by correlation ID."""
    replay_config = ReplayConfig(enabled=True)
    bus = LocalEventBus(replay_config=replay_config)
    
    await bus.start()
    
    correlation_id = "workflow-123"
    
    # Publish related events
    for i in range(5):
        event = EventMessage(
            event_type="workflow.step",
            data={"step": i},
            correlation_id=correlation_id
        )
        await bus.publish(event)
    
    # Publish unrelated events
    for i in range(3):
        event = EventMessage(
            event_type="other.event",
            data={"value": i}
        )
        await bus.publish(event)
    
    await asyncio.sleep(0.1)
    
    # Get history by correlation ID
    history = await bus.get_event_history(correlation_id=correlation_id)
    
    assert len(history) == 5
    assert all(e.correlation_id == correlation_id for e in history)
    
    await bus.stop()


@pytest.mark.asyncio
async def test_deduplication_cache_size_limit():
    """Test that deduplication cache respects size limits."""
    dedup_config = DeduplicationConfig(
        enabled=True,
        window_seconds=3600,  # Long window
        max_cache_size=5  # Small cache
    )
    bus = LocalEventBus(dedup_config=dedup_config)
    
    await bus.start()
    
    # Publish more events than cache size
    for i in range(10):
        event = EventMessage(
            event_type="test.event",
            data={"index": i}
        )
        await bus.publish(event)
    
    # Cache should not exceed max size
    assert len(bus._dedup_cache) <= dedup_config.max_cache_size
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_replay_with_filters():
    """Test event replay with multiple filters."""
    replay_config = ReplayConfig(enabled=True)
    bus = LocalEventBus(replay_config=replay_config)
    
    await bus.start()
    
    # Publish events to different topics
    await bus.publish(
        EventMessage(event_type="app.started", data={"version": "1.0"}),
        topic="system"
    )
    
    await bus.publish(
        EventMessage(event_type="user.login", data={"user": "alice"}),
        topic="auth"
    )
    
    await bus.publish(
        EventMessage(event_type="user.logout", data={"user": "alice"}),
        topic="auth"
    )
    
    await asyncio.sleep(0.1)
    
    # Replay only auth topic events
    replayed = await bus.replay_events(
        start_time=datetime.utcnow() - timedelta(minutes=1),
        topic="auth"
    )
    
    assert len(replayed) == 2
    assert all(e.event_type.startswith("user.") for e in replayed)
    
    await bus.stop()


@pytest.mark.asyncio
async def test_deduplication_disabled():
    """Test that deduplication can be disabled."""
    dedup_config = DeduplicationConfig(enabled=False)
    bus = LocalEventBus(dedup_config=dedup_config)
    
    await bus.start()
    
    received_events = []
    
    async def handler(event: EventMessage):
        received_events.append(event)
    
    await bus.subscribe("test.event", handler)
    
    # Publish identical events
    event_data = {"value": 42}
    
    await bus.publish(EventMessage(event_type="test.event", data=event_data))
    await bus.publish(EventMessage(event_type="test.event", data=event_data))
    
    await asyncio.sleep(0.1)
    
    # Should receive both events when dedup is disabled
    assert len(received_events) == 2
    
    await bus.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])