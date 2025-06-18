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
)

logger = logging.getLogger(__name__)


class LocalEventBus(EventBus):
    """In-memory event bus implementation using asyncio."""

    def __init__(self, **kwargs: Any):
        self._topics: Dict[str, asyncio.Queue] = {}
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._handlers: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._dead_letter_queue: List[tuple[EventMessage, str]] = []
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._max_retries = kwargs.get("max_retries", 3)
        self._retry_delay = kwargs.get("retry_delay", 1.0)

    async def publish(self, event: EventMessage, topic: Optional[str] = None) -> None:
        """Publish an event to the event bus."""
        topic = topic or "default"

        if topic not in self._topics:
            await self.create_topic(topic)

        # Put event in the queue
        await self._topics[topic].put(event)
        logger.debug(f"Published event {event.id} to topic {topic}")

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

        # Process with each matching handler
        for subscription in matching_subscriptions:
            if self._matches_filter(event, subscription.filter_expression):
                await self._invoke_handler(subscription, event, topic)

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
