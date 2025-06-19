# Lightning Core: Orphaned Events Solution

## Overview

This document describes the solution implemented to prevent event accumulation when events have no consumers in the Lightning Core event-driven architecture.

## Problem Statement

In the original implementation, events published to the event bus would accumulate indefinitely if there were no subscribers or drivers registered to handle them. This could lead to:
- Memory exhaustion in local mode
- Queue buildup in cloud providers (Azure Service Bus, Redis)
- Performance degradation over time
- Unnecessary resource consumption

## Solution Components

### 1. Orphaned Event Detection

Added detection mechanisms across all event bus providers to identify events with no active subscribers:

- **LocalEventBus**: Tracks orphaned events in memory with configurable limits
- **Azure Service Bus**: Routes orphaned events to dead letter queue with "NoSubscribers" reason
- **Redis EventBus**: Stores orphaned events with special keys and TTL

### 2. Automatic Drainage

The Universal Event Processor now checks for consumers before processing:

```python
# Check if event has any consumers (drivers or direct subscribers)
has_drivers = bool(self.driver_registry.get_drivers_by_capability(event.type))
has_subscribers = await self.event_bus.has_subscribers(event.type)

if not has_drivers and not has_subscribers:
    # Event is drained to prevent accumulation
    await self.metrics.record_orphaned_event(event)
    return []
```

### 3. TTL Configuration

Events now support Time-To-Live (TTL) configuration:

- Default TTL can be set per provider (default: 1 hour)
- Events automatically expire and are dropped during processing
- Background cleanup task removes expired events periodically

### 4. Monitoring and Metrics

Added comprehensive monitoring capabilities:

- **EventMonitor** class provides health status and metrics
- Tracks orphaned event counts by type
- Provides recommendations for handling high orphan rates
- Exposes cleanup operations for manual intervention

### 5. Event Bus API Extensions

New methods added to the EventBus abstract interface:

- `has_subscribers(event_type)`: Check if an event type has active subscribers
- `get_orphaned_events()`: Retrieve orphaned events for inspection
- `drain_orphaned_events()`: Manually remove orphaned events

## Usage Examples

### Check Event Health

```python
from lightning_core.vextir_os.event_monitoring import get_event_monitor

monitor = get_event_monitor()
health = await monitor.get_health_status()

if health["status"] == "unhealthy":
    print(f"High orphan rate: {health['metrics']['orphan_rate']}")
```

### Manual Cleanup

```python
# Clean up orphaned events older than 24 hours
result = await monitor.cleanup_orphaned_events(
    older_than_hours=24,
    event_types=["obsolete.event.type"]
)
print(f"Drained {result['drained_count']} events")
```

### Configure TTL

```python
# Set default TTL when creating event bus
event_bus = LocalEventBus(default_ttl_seconds=3600)  # 1 hour

# Or set per event
event = EventMessage(
    event_type="temporary.event",
    data={"temp": "data"},
    ttl_seconds=300  # 5 minutes
)
```

## Provider-Specific Implementation

### Local Provider
- In-memory tracking of orphaned events
- Automatic history pruning at 10,000 events
- Background cleanup task every 5 minutes

### Azure Service Bus
- Uses native dead letter queue functionality
- Orphaned events marked with "NoSubscribers" reason
- Requires management API for advanced queries

### Redis Provider
- Stores orphaned events with "orphaned:" key prefix
- 24-hour TTL on orphaned event storage
- Efficient scanning with Redis SCAN command

## Testing

Comprehensive test suite added in `tests/test_event_drainage_simple.py`:

- Orphaned event detection
- Subscriber presence validation
- Wildcard pattern matching
- TTL expiration
- Drainage operations
- Monitoring functionality

## Best Practices

1. **Register handlers early**: Ensure event handlers/drivers are registered before publishing events
2. **Use wildcards carefully**: Wildcard subscribers can prevent legitimate orphaning
3. **Monitor regularly**: Check orphan rates as part of system health monitoring
4. **Clean up periodically**: Schedule regular cleanup of old orphaned events
5. **Set appropriate TTLs**: Balance between reliability and resource usage

## Migration Notes

The solution is backward compatible. Existing systems will benefit from:
- Automatic orphan detection (can be disabled with `track_orphaned=False`)
- Default TTL application (configurable per provider)
- No breaking changes to existing APIs

## Future Improvements

1. **Smart TTL adjustment**: Automatically adjust TTL based on event patterns
2. **Event replay**: Allow reprocessing of orphaned events when handlers are added
3. **Advanced filtering**: More sophisticated orphan detection rules
4. **Cloud provider optimizations**: Better integration with native dead letter queue features