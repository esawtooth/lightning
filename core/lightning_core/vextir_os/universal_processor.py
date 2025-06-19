"""
Vextir OS Universal Event Processor - Core event processing engine
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .drivers import DriverRegistry, get_driver_registry
from .event_bus import EventBus, get_event_bus
from .events import Event
from .registries import (
    ModelRegistry,
    get_model_registry,
)
# Use new simplified tool registry
from ..tools import get_tool_registry
from .security import SecurityManager, get_security_manager


class EventProcessingError(Exception):
    """Error during event processing"""

    pass


class UniversalEventProcessor:
    """Single Azure Function that processes all events according to Vextir OS spec"""

    def __init__(self):
        self.event_bus = get_event_bus()
        self.driver_registry = get_driver_registry()
        self.security_manager = get_security_manager()
        self.model_registry = get_model_registry()
        self.tool_registry = get_tool_registry()
        self.metrics = EventMetrics()

    async def process_event(self, event: Event) -> List[Event]:
        """Main event processing loop"""
        start_time = time.time()
        output_events = []

        try:
            # 1. Validate event
            if not self._validate_event(event):
                raise EventProcessingError(f"Invalid event: {event}")

            # 2. Apply security policies
            if not await self.security_manager.authorize(event):
                raise EventProcessingError(f"Unauthorized event: {event}")

            # 3. Check if event has any consumers (drivers or direct subscribers)
            has_drivers = bool(self.driver_registry.get_drivers_by_capability(event.type))
            has_subscribers = await self.event_bus.has_subscribers(event.type)
            
            if not has_drivers and not has_subscribers:
                logging.warning(
                    f"Event {event.type} has no consumers (no drivers or subscribers). "
                    f"Event will be drained to prevent accumulation."
                )
                # Record as orphaned for monitoring
                await self.metrics.record_orphaned_event(event)
                return []  # Return empty list - event is effectively drained

            # 4. Route to drivers
            driver_events = await self.driver_registry.route_event(event)
            output_events.extend(driver_events)

            # 4. Queue output events
            for output_event in output_events:
                output_event.correlation_id = event.id
                await self.event_bus.emit(output_event)

            # 5. Update metrics
            processing_time = time.time() - start_time
            await self.metrics.record_event(event, output_events, processing_time)

            logging.info(
                f"Processed event {event.type} -> {len(output_events)} output events"
            )

        except Exception as e:
            # Create error event
            error_event = Event(
                timestamp=datetime.utcnow(),
                source="UniversalEventProcessor",
                type="error",
                user_id=event.user_id,
                metadata={
                    "original_event": event.to_dict(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            output_events.append(error_event)

            # Update error metrics
            processing_time = time.time() - start_time
            await self.metrics.record_error(event, str(e), processing_time)

            logging.error(f"Error processing event {event.type}: {e}")

        return output_events

    def _validate_event(self, event: Event) -> bool:
        """Validate event structure and required fields"""
        if not event.id:
            return False
        if not event.type:
            return False
        if not event.user_id:
            return False
        if not event.source:
            return False
        return True

    async def get_metrics(self) -> Dict[str, Any]:
        """Get processing metrics"""
        return await self.metrics.get_summary()


class EventMetrics:
    """Metrics collection for event processing"""

    def __init__(self):
        self.total_events = 0
        self.total_errors = 0
        self.total_orphaned = 0
        self.processing_times = []
        self.event_types = {}
        self.error_types = {}
        self.orphaned_types = {}
        self.max_metrics = 10000

    async def record_event(
        self, event: Event, output_events: List[Event], processing_time: float
    ):
        """Record successful event processing"""
        self.total_events += 1
        self.processing_times.append(processing_time)

        # Track event types
        if event.type not in self.event_types:
            self.event_types[event.type] = 0
        self.event_types[event.type] += 1

        # Limit metrics size
        if len(self.processing_times) > self.max_metrics:
            self.processing_times = self.processing_times[-self.max_metrics // 2 :]

    async def record_error(self, event: Event, error: str, processing_time: float):
        """Record event processing error"""
        self.total_errors += 1
        self.processing_times.append(processing_time)

        # Track error types
        error_type = error.split(":")[0] if ":" in error else "Unknown"
        if error_type not in self.error_types:
            self.error_types[error_type] = 0
        self.error_types[error_type] += 1

    async def record_orphaned_event(self, event: Event):
        """Record an orphaned event that has no consumers"""
        self.total_orphaned += 1
        
        # Track orphaned event types
        if event.type not in self.orphaned_types:
            self.orphaned_types[event.type] = 0
        self.orphaned_types[event.type] += 1

    async def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        avg_processing_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times
            else 0
        )

        return {
            "total_events": self.total_events,
            "total_errors": self.total_errors,
            "total_orphaned": self.total_orphaned,
            "error_rate": self.total_errors / max(self.total_events, 1),
            "orphan_rate": self.total_orphaned / max(self.total_events, 1),
            "avg_processing_time_ms": avg_processing_time * 1000,
            "event_types": self.event_types,
            "error_types": self.error_types,
            "orphaned_types": self.orphaned_types,
        }


# Global processor instance
_global_processor: Optional[UniversalEventProcessor] = None


def get_universal_processor() -> UniversalEventProcessor:
    """Get global universal processor instance"""
    global _global_processor
    if _global_processor is None:
        _global_processor = UniversalEventProcessor()
    return _global_processor


async def process_event_message(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process event from Azure Service Bus message"""
    try:
        # Parse event
        event = Event.from_dict(event_data)

        # Process through universal processor
        processor = get_universal_processor()
        output_events = await processor.process_event(event)

        return {
            "status": "success",
            "input_event": event.to_dict(),
            "output_events": [e.to_dict() for e in output_events],
            "output_count": len(output_events),
        }

    except Exception as e:
        logging.error(f"Failed to process event: {e}")
        return {"status": "error", "error": str(e), "input_event": event_data}
