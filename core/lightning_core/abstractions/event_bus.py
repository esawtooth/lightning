"""
Event bus abstraction layer for Lightning Core.

Provides abstract base classes for event-driven communication,
supporting both cloud (e.g., Azure Service Bus) and local implementations.
"""

import hashlib
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from .health import HealthCheckable, HealthCheckResult, HealthStatus


class EventPriority(Enum):
    """Event priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EventMessage:
    """Base event message class."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    ttl_seconds: Optional[int] = None  # Default TTL can be set per provider
    idempotency_key: Optional[str] = None  # For explicit deduplication
    _fingerprint: Optional[str] = field(default=None, init=False, repr=False)

    def is_expired(self) -> bool:
        """Check if the event has expired based on TTL."""
        if self.ttl_seconds is None:
            return False
        
        age_seconds = (datetime.utcnow() - self.timestamp).total_seconds()
        return age_seconds > self.ttl_seconds

    def get_fingerprint(self) -> str:
        """Generate a fingerprint for deduplication."""
        if self._fingerprint:
            return self._fingerprint
        
        # Use idempotency key if provided
        if self.idempotency_key:
            self._fingerprint = self.idempotency_key
            return self._fingerprint
        
        # Generate fingerprint from event content
        fingerprint_data = {
            "event_type": self.event_type,
            "data": self.data,
            "correlation_id": self.correlation_id,
        }
        
        # Create deterministic JSON string
        json_str = json.dumps(fingerprint_data, sort_keys=True, default=str)
        self._fingerprint = hashlib.sha256(json_str.encode()).hexdigest()
        
        return self._fingerprint

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(
            {
                "id": self.id,
                "event_type": self.event_type,
                "data": self.data,
                "metadata": self.metadata,
                "timestamp": self.timestamp.isoformat(),
                "priority": self.priority.value,
                "correlation_id": self.correlation_id,
                "reply_to": self.reply_to,
                "ttl_seconds": self.ttl_seconds,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "EventMessage":
        """Create event from JSON string."""
        data = json.loads(json_str)
        event = cls()
        event.id = data.get("id", event.id)
        event.event_type = data.get("event_type", "")
        event.data = data.get("data", {})
        event.metadata = data.get("metadata", {})

        if "timestamp" in data:
            event.timestamp = datetime.fromisoformat(data["timestamp"])

        if "priority" in data:
            event.priority = EventPriority(data["priority"])

        event.correlation_id = data.get("correlation_id")
        event.reply_to = data.get("reply_to")
        event.ttl_seconds = data.get("ttl_seconds")

        return event


EventHandler = Callable[[EventMessage], Awaitable[None]]


class EventSubscription:
    """Represents an event subscription."""

    def __init__(
        self,
        subscription_id: str,
        event_type: str,
        handler: EventHandler,
        filter_expression: Optional[Dict[str, Any]] = None,
    ):
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.handler = handler
        self.filter_expression = filter_expression or {}


@dataclass
class DeduplicationConfig:
    """Configuration for event deduplication."""
    enabled: bool = True
    window_seconds: int = 300  # 5 minutes default
    max_cache_size: int = 10000
    
    
@dataclass 
class ReplayConfig:
    """Configuration for event replay."""
    enabled: bool = True
    max_history_size: int = 100000
    retention_seconds: int = 86400  # 24 hours default


class EventBus(ABC, HealthCheckable):
    """Abstract base class for event bus implementations."""
    
    def __init__(self, dedup_config: Optional[DeduplicationConfig] = None,
                 replay_config: Optional[ReplayConfig] = None):
        """Initialize event bus with optional deduplication and replay configs."""
        self.dedup_config = dedup_config or DeduplicationConfig()
        self.replay_config = replay_config or ReplayConfig()

    @abstractmethod
    async def publish(self, event: EventMessage, topic: Optional[str] = None) -> None:
        """Publish an event to the event bus."""
        pass

    @abstractmethod
    async def publish_batch(
        self, events: List[EventMessage], topic: Optional[str] = None
    ) -> None:
        """Publish multiple events as a batch."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        topic: Optional[str] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Subscribe to events of a specific type.
        Returns a subscription ID that can be used to unsubscribe.
        """
        pass

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events using subscription ID."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the event bus (begin processing events)."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event bus (stop processing events)."""
        pass

    @abstractmethod
    async def create_topic(self, topic_name: str) -> None:
        """Create a new topic/queue if it doesn't exist."""
        pass

    @abstractmethod
    async def delete_topic(self, topic_name: str) -> None:
        """Delete a topic/queue."""
        pass

    @abstractmethod
    async def topic_exists(self, topic_name: str) -> bool:
        """Check if a topic/queue exists."""
        pass

    @abstractmethod
    async def get_dead_letter_events(
        self, topic: Optional[str] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Retrieve events from dead letter queue."""
        pass

    @abstractmethod
    async def reprocess_dead_letter_event(
        self, event_id: str, topic: Optional[str] = None
    ) -> None:
        """Reprocess a dead letter event."""
        pass

    async def has_subscribers(self, event_type: str, topic: Optional[str] = None) -> bool:
        """
        Check if an event type has any active subscribers.

        Args:
            event_type: Event type to check
            topic: Optional topic to check

        Returns:
            True if there are active subscribers
        """
        # Default implementation - providers can override for efficiency
        return True  # Conservative default to avoid dropping events

    async def get_orphaned_events(
        self, since: Optional[datetime] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """
        Get events that were published but had no subscribers.

        Args:
            since: Optional timestamp to filter events after
            max_items: Maximum number of events to retrieve

        Returns:
            List of orphaned events
        """
        # Default implementation - providers should override
        return []

    async def drain_orphaned_events(
        self, event_types: Optional[List[str]] = None, before: Optional[datetime] = None
    ) -> int:
        """
        Remove orphaned events from the system.

        Args:
            event_types: Optional list of event types to drain (None = all)
            before: Optional timestamp to drain events before

        Returns:
            Number of events drained
        """
        # Default implementation - providers should override
        return 0

    @abstractmethod
    async def replay_events(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        topic: Optional[str] = None,
    ) -> List[EventMessage]:
        """
        Replay events from history within a time range.

        Args:
            start_time: Start of the replay window
            end_time: End of the replay window (None = now)
            event_types: Optional list of event types to replay
            topic: Optional topic to filter by

        Returns:
            List of events to replay
        """
        pass

    @abstractmethod
    async def get_event_history(
        self,
        event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventMessage]:
        """
        Get event history by ID or correlation ID.

        Args:
            event_id: Optional specific event ID
            correlation_id: Optional correlation ID to track related events
            limit: Maximum number of events to return

        Returns:
            List of historical events
        """
        pass
    
    async def health_check(self) -> HealthCheckResult:
        """
        Default health check implementation for event bus providers.
        Providers should override this for specific health checks.
        """
        start_time = time.time()
        try:
            # Try to check if default topic exists
            exists = await self.topic_exists("default")
            latency_ms = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                status=HealthStatus.HEALTHY if exists else HealthStatus.DEGRADED,
                latency_ms=latency_ms,
                details={"default_topic_exists": exists}
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )
