"""
Local in-memory event bus implementation.

Uses asyncio queues for event routing and processing.
"""

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from lightning_core.abstractions.event_bus import (
    EventBus,
    EventHandler,
    EventMessage,
    EventSubscription,
    DeduplicationConfig,
    ReplayConfig,
)

logger = logging.getLogger(__name__)


class LocalEventBus(EventBus):
    """In-memory event bus implementation using asyncio."""

    def __init__(self, **kwargs: Any):
        # Initialize parent with dedup and replay configs
        dedup_config = kwargs.pop("dedup_config", None)
        replay_config = kwargs.pop("replay_config", None)
        super().__init__(dedup_config, replay_config)
        
        self._topics: Dict[str, asyncio.Queue] = {}
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._handlers: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._dead_letter_queue: List[tuple[EventMessage, str]] = []
        self._orphaned_events: List[tuple[EventMessage, str]] = []
        self._event_history: List[tuple[EventMessage, str, datetime]] = []
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._max_retries = kwargs.get("max_retries", 3)
        self._retry_delay = kwargs.get("retry_delay", 1.0)
        self._max_history_size = kwargs.get("max_history_size", 10000)
        self._track_orphaned = kwargs.get("track_orphaned", True)
        self._default_ttl_seconds = kwargs.get("default_ttl_seconds", 3600)  # 1 hour default
        
        # Deduplication cache: fingerprint -> (event_id, timestamp)
        self._dedup_cache: Dict[str, tuple[str, datetime]] = {}
        self._dedup_lock = asyncio.Lock()

    async def publish(self, event: EventMessage, topic: Optional[str] = None) -> None:
        """Publish an event to the event bus."""
        topic = topic or "default"

        if topic not in self._topics:
            await self.create_topic(topic)

        # Apply default TTL if not set
        if event.ttl_seconds is None:
            event.ttl_seconds = self._default_ttl_seconds

        # Check for duplicate if deduplication is enabled
        if self.dedup_config.enabled:
            fingerprint = event.get_fingerprint()
            
            async with self._dedup_lock:
                # Check if we've seen this event before
                if fingerprint in self._dedup_cache:
                    cached_id, cached_time = self._dedup_cache[fingerprint]
                    age_seconds = (datetime.utcnow() - cached_time).total_seconds()
                    
                    # If within deduplication window, skip
                    if age_seconds < self.dedup_config.window_seconds:
                        logger.info(
                            f"Duplicate event detected and skipped: {event.event_type} "
                            f"(fingerprint: {fingerprint[:8]}..., original: {cached_id})"
                        )
                        return
                
                # Add to dedup cache
                self._dedup_cache[fingerprint] = (event.id, datetime.utcnow())
                
                # Maintain cache size
                if len(self._dedup_cache) > self.dedup_config.max_cache_size:
                    # Remove oldest entries
                    sorted_entries = sorted(
                        self._dedup_cache.items(),
                        key=lambda x: x[1][1]  # Sort by timestamp
                    )
                    to_remove = len(self._dedup_cache) - self.dedup_config.max_cache_size
                    for fp, _ in sorted_entries[:to_remove]:
                        del self._dedup_cache[fp]

        # Put event in the queue
        await self._topics[topic].put(event)
        logger.debug(f"Published event {event.id} to topic {topic} with TTL {event.ttl_seconds}s")

    async def publish_batch(
        self, events: List[EventMessage], topic: Optional[str] = None
    ) -> None:
        """Publish multiple events as a batch."""
        for event in events:
            await self.publish(event, topic)

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        topic: Optional[str] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Subscribe to events of a specific type."""
        subscription_id = str(uuid.uuid4())
        topic = topic or "default"

        subscription = EventSubscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler=handler,
            filter_expression=filter_expression,
        )

        self._subscriptions[subscription_id] = subscription
        self._handlers[event_type].append(subscription)

        # Ensure topic exists
        if topic not in self._topics:
            await self.create_topic(topic)

        logger.info(f"Created subscription {subscription_id} for {event_type}")
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events using subscription ID."""
        if subscription_id not in self._subscriptions:
            return

        subscription = self._subscriptions[subscription_id]
        self._handlers[subscription.event_type].remove(subscription)
        del self._subscriptions[subscription_id]

        logger.info(f"Removed subscription {subscription_id}")

    async def start(self) -> None:
        """Start the event bus (begin processing events)."""
        if self._running:
            return

        self._running = True

        # Start processing tasks for each topic
        for topic in self._topics:
            task = asyncio.create_task(self._process_topic(topic))
            self._tasks.add(task)

        # Start cleanup task for expired events
        cleanup_task = asyncio.create_task(self._cleanup_expired_events())
        self._tasks.add(cleanup_task)

        logger.info("Local event bus started")

    async def stop(self) -> None:
        """Stop the event bus (stop processing events)."""
        self._running = False

        # Cancel all processing tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("Local event bus stopped")

    async def create_topic(self, topic_name: str) -> None:
        """Create a new topic/queue if it doesn't exist."""
        if topic_name not in self._topics:
            self._topics[topic_name] = asyncio.Queue()

            # If already running, start processing this topic
            if self._running:
                task = asyncio.create_task(self._process_topic(topic_name))
                self._tasks.add(task)

    async def delete_topic(self, topic_name: str) -> None:
        """Delete a topic/queue."""
        if topic_name in self._topics:
            del self._topics[topic_name]

    async def topic_exists(self, topic_name: str) -> bool:
        """Check if a topic/queue exists."""
        return topic_name in self._topics

    async def get_dead_letter_events(
        self, topic: Optional[str] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Retrieve events from dead letter queue."""
        if topic:
            events = [e for e, t in self._dead_letter_queue if t == topic]
        else:
            events = [e for e, t in self._dead_letter_queue]

        if max_items:
            events = events[:max_items]

        return events

    async def reprocess_dead_letter_event(
        self, event_id: str, topic: Optional[str] = None
    ) -> None:
        """Reprocess a dead letter event."""
        # Find and remove the event from dead letter queue
        for i, (event, event_topic) in enumerate(self._dead_letter_queue):
            if event.id == event_id:
                if topic and event_topic != topic:
                    continue

                # Remove from dead letter queue
                self._dead_letter_queue.pop(i)

                # Republish the event
                await self.publish(event, event_topic)
                logger.info(f"Reprocessing dead letter event {event_id}")
                return

        raise ValueError(f"Dead letter event not found: {event_id}")

    async def _process_topic(self, topic: str) -> None:
        """Process events from a specific topic."""
        logger.info(f"Started processing topic: {topic}")

        while self._running:
            try:
                # Wait for events with timeout to allow checking _running
                try:
                    event = await asyncio.wait_for(
                        self._topics[topic].get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Process the event
                await self._process_event(event, topic)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing topic {topic}: {e}")

        logger.info(f"Stopped processing topic: {topic}")

    async def _process_event(self, event: EventMessage, topic: str) -> None:
        """Process a single event."""
        # Check if event has expired
        if event.is_expired():
            logger.warning(f"Expired event dropped: {event.event_type} (ID: {event.id})")
            return

        # Track event in history for replay if enabled
        if self.replay_config.enabled:
            self._event_history.append((event, topic, datetime.utcnow()))
            
            # Maintain history size limit
            if len(self._event_history) > self.replay_config.max_history_size:
                # Remove oldest entries
                self._event_history = self._event_history[-self.replay_config.max_history_size:]
            
            # Clean up old events based on retention
            cutoff_time = datetime.utcnow() - timedelta(seconds=self.replay_config.retention_seconds)
            self._event_history = [
                (e, t, ts) for e, t, ts in self._event_history
                if ts > cutoff_time
            ]

        # Find matching subscriptions
        matching_subscriptions = []

        # Direct event type matches
        if event.event_type in self._handlers:
            matching_subscriptions.extend(self._handlers[event.event_type])

        # Wildcard matches (e.g., "user.*" matches "user.created")
        for pattern, subscriptions in self._handlers.items():
            if "*" in pattern:
                regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
                if re.match(f"^{regex_pattern}$", event.event_type):
                    matching_subscriptions.extend(subscriptions)

        # Check if event is orphaned (no matching subscriptions)
        if not matching_subscriptions and self._track_orphaned:
            logger.warning(f"Orphaned event detected: {event.event_type} (ID: {event.id})")
            self._orphaned_events.append((event, topic))
            # Limit orphaned events storage
            if len(self._orphaned_events) > 1000:
                self._orphaned_events = self._orphaned_events[-1000:]
            return

        # Process with each matching handler
        handled = False
        for subscription in matching_subscriptions:
            if self._matches_filter(event, subscription.filter_expression):
                await self._invoke_handler(subscription, event, topic)
                handled = True

        # Track if event had subscribers but none handled it (due to filters)
        if not handled and self._track_orphaned:
            logger.info(f"Event {event.event_type} had subscribers but was filtered out")

    def _matches_filter(
        self, event: EventMessage, filter_expression: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if event matches filter expression."""
        if not filter_expression:
            return True

        # Simple filter implementation - all conditions must match
        for key, expected_value in filter_expression.items():
            if key.startswith("data."):
                # Check data fields
                field_path = key[5:].split(".")
                value = event.data
                for field in field_path:
                    if isinstance(value, dict) and field in value:
                        value = value[field]
                    else:
                        return False
                if value != expected_value:
                    return False
            elif key.startswith("metadata."):
                # Check metadata fields
                field = key[9:]
                if event.metadata.get(field) != expected_value:
                    return False
            elif hasattr(event, key):
                # Check event attributes
                if getattr(event, key) != expected_value:
                    return False

        return True

    async def _invoke_handler(
        self,
        subscription: EventSubscription,
        event: EventMessage,
        topic: str,
        retry_count: int = 0,
    ) -> None:
        """Invoke an event handler with retry logic."""
        try:
            await subscription.handler(event)
            logger.debug(
                f"Successfully processed event {event.id} with handler {subscription.subscription_id}"
            )
        except Exception as e:
            logger.error(
                f"Error in handler {subscription.subscription_id} for event {event.id}: {e}"
            )

            if retry_count < self._max_retries:
                # Retry with exponential backoff
                await asyncio.sleep(self._retry_delay * (2**retry_count))
                await self._invoke_handler(subscription, event, topic, retry_count + 1)
            else:
                # Move to dead letter queue
                self._dead_letter_queue.append((event, topic))
                logger.error(
                    f"Event {event.id} moved to dead letter queue after {retry_count} retries"
                )

    async def has_subscribers(self, event_type: str, topic: Optional[str] = None) -> bool:
        """Check if an event type has any active subscribers."""
        # Check direct matches
        if event_type in self._handlers and self._handlers[event_type]:
            return True

        # Check wildcard patterns
        for pattern, subscriptions in self._handlers.items():
            if "*" in pattern and subscriptions:  # Check if pattern has active subscriptions
                regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
                if re.match(f"^{regex_pattern}$", event_type):
                    return True

        return False

    async def get_orphaned_events(
        self, since: Optional[datetime] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Get events that were published but had no subscribers."""
        events = []
        
        for event, topic in self._orphaned_events:
            if since and event.timestamp < since:
                continue
            events.append(event)
            
            if max_items and len(events) >= max_items:
                break

        return events

    async def drain_orphaned_events(
        self, event_types: Optional[List[str]] = None, before: Optional[datetime] = None
    ) -> int:
        """Remove orphaned events from the system."""
        count = 0
        new_orphaned = []

        for event, topic in self._orphaned_events:
            should_drain = True

            # Check event type filter
            if event_types and event.event_type not in event_types:
                should_drain = False

            # Check timestamp filter
            if before and event.timestamp >= before:
                should_drain = False

            if should_drain:
                count += 1
                logger.info(f"Draining orphaned event: {event.event_type} (ID: {event.id})")
            else:
                new_orphaned.append((event, topic))

        self._orphaned_events = new_orphaned
        return count

    async def _cleanup_expired_events(self):
        """Background task to clean up expired events."""
        cleanup_interval = 300  # 5 minutes
        
        while self._running:
            try:
                await asyncio.sleep(cleanup_interval)
                
                # Clean up expired orphaned events
                original_count = len(self._orphaned_events)
                self._orphaned_events = [
                    (event, topic) for event, topic in self._orphaned_events
                    if not event.is_expired()
                ]
                removed_count = original_count - len(self._orphaned_events)
                
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} expired orphaned events")
                
                # Clean up expired events from history
                original_history = len(self._event_history)
                self._event_history = [
                    (event, topic, ts) for event, topic, ts in self._event_history
                    if not event.is_expired()
                ]
                history_removed = original_history - len(self._event_history)
                
                if history_removed > 0:
                    logger.debug(f"Cleaned up {history_removed} expired events from history")
                
                # Clean up old deduplication cache entries
                if self.dedup_config.enabled:
                    async with self._dedup_lock:
                        cutoff_time = datetime.utcnow() - timedelta(seconds=self.dedup_config.window_seconds)
                        original_dedup = len(self._dedup_cache)
                        
                        # Remove entries older than dedup window
                        self._dedup_cache = {
                            fp: (event_id, ts)
                            for fp, (event_id, ts) in self._dedup_cache.items()
                            if ts > cutoff_time
                        }
                        
                        dedup_removed = original_dedup - len(self._dedup_cache)
                        if dedup_removed > 0:
                            logger.debug(f"Cleaned up {dedup_removed} expired deduplication entries")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                
        logger.info("Cleanup task stopped")

    async def replay_events(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        topic: Optional[str] = None,
    ) -> List[EventMessage]:
        """Replay events from history within a time range."""
        if not self.replay_config.enabled:
            logger.warning("Event replay is disabled")
            return []
        
        end_time = end_time or datetime.utcnow()
        replayed_events = []
        
        for event, event_topic, timestamp in self._event_history:
            # Check time range
            if timestamp < start_time or timestamp > end_time:
                continue
                
            # Check topic filter
            if topic and event_topic != topic:
                continue
                
            # Check event type filter
            if event_types and event.event_type not in event_types:
                continue
                
            replayed_events.append(event)
        
        logger.info(
            f"Replaying {len(replayed_events)} events from {start_time} to {end_time}"
        )
        
        return replayed_events

    async def get_event_history(
        self,
        event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventMessage]:
        """Get event history by ID or correlation ID."""
        if not self.replay_config.enabled:
            logger.warning("Event replay is disabled")
            return []
        
        history = []
        
        for event, _, _ in reversed(self._event_history):
            # Check event ID
            if event_id and event.id == event_id:
                history.append(event)
                if not correlation_id:  # If only looking for specific event
                    break
                    
            # Check correlation ID
            if correlation_id and event.correlation_id == correlation_id:
                history.append(event)
                
            # Check limit
            if limit and len(history) >= limit:
                break
        
        return history
