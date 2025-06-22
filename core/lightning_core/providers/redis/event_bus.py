"""
Redis-based event bus implementation.

Uses Redis Pub/Sub for event messaging, suitable for local development
and small-scale deployments.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as redis

from lightning_core.abstractions.event_bus import (
    EventBus,
    EventHandler,
    EventMessage,
    EventSubscription,
)

logger = logging.getLogger(__name__)


class RedisEventBus(EventBus):
    """Redis-based event bus implementation."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        endpoint: Optional[str] = None,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        **kwargs: Any,
    ):
        # Redis connection - prioritize connection_string, then endpoint, then host/port
        if connection_string:
            self._redis = redis.from_url(connection_string, decode_responses=True)
        elif endpoint:
            self._redis = redis.from_url(endpoint, decode_responses=True)
        else:
            self._redis = redis.Redis(
                host=host, port=port, db=db, decode_responses=True
            )

        # Pub/Sub instance
        self._pubsub = self._redis.pubsub()

        # Local subscription tracking
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._handlers: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None

        # Dead letter storage (using Redis lists)
        self._dead_letter_prefix = "dead_letter:"
        self._max_retries = kwargs.get("max_retries", 3)

    async def publish(self, event: EventMessage, topic: Optional[str] = None) -> None:
        """Publish an event to the event bus."""
        channel = self._get_channel_name(topic, event.event_type)

        # Publish to Redis - let Redis handle pattern matching for subscriptions
        await self._redis.publish(channel, event.to_json())

        logger.debug(f"Published event {event.id} to channel {channel}")

    async def publish_batch(
        self, events: List[EventMessage], topic: Optional[str] = None
    ) -> None:
        """Publish multiple events as a batch."""
        # Redis doesn't have native batch publish, so we use a pipeline
        async with self._redis.pipeline() as pipe:
            for event in events:
                channel = self._get_channel_name(topic, event.event_type)
                pipe.publish(channel, event.to_json())

            await pipe.execute()

        logger.debug(f"Published batch of {len(events)} events")

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        topic: Optional[str] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Subscribe to events of a specific type."""
        subscription_id = str(uuid.uuid4())

        subscription = EventSubscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler=handler,
            filter_expression=filter_expression,
        )

        self._subscriptions[subscription_id] = subscription
        self._handlers[event_type].append(subscription)

        # Subscribe to Redis channel
        channel = self._get_channel_name(topic, event_type)
        
        # Use pattern subscription for wildcards
        if "*" in event_type:
            await self._pubsub.psubscribe(channel)
            logger.info(
                f"Created pattern subscription {subscription_id} for {event_type} on pattern {channel}"
            )
        else:
            await self._pubsub.subscribe(channel)
            logger.info(
                f"Created subscription {subscription_id} for {event_type} on channel {channel}"
            )
        
        # Start listener on first subscription if running
        if self._running and self._listener_task is None:
            logger.info("Starting Redis listener task on first subscription")
            self._listener_task = asyncio.create_task(self._listen_for_messages())
        elif self._running and self._listener_task and self._listener_task.done():
            # Restart listener if it stopped
            logger.info("Restarting Redis listener task (previous task completed)")
            self._listener_task = asyncio.create_task(self._listen_for_messages())
            
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events using subscription ID."""
        if subscription_id not in self._subscriptions:
            return

        subscription = self._subscriptions[subscription_id]
        self._handlers[subscription.event_type].remove(subscription)

        # Check if we still need this channel
        if not self._handlers[subscription.event_type]:
            channel = self._get_channel_name(None, subscription.event_type)
            if "*" in subscription.event_type:
                await self._pubsub.punsubscribe(channel)
            else:
                await self._pubsub.unsubscribe(channel)

        del self._subscriptions[subscription_id]
        logger.info(f"Removed subscription {subscription_id}")

    async def start(self) -> None:
        """Start the event bus (begin processing events)."""
        if self._running:
            return

        self._running = True

        # Don't start listener yet - will start when first subscription is added
        logger.info("Redis event bus started (listener will start on first subscription)")

    async def stop(self) -> None:
        """Stop the event bus (stop processing events)."""
        self._running = False

        # Stop listening
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from all channels
        await self._pubsub.unsubscribe()

        # Close connections
        await self._pubsub.close()
        await self._redis.close()

        logger.info("Redis event bus stopped")

    async def create_topic(self, topic_name: str) -> None:
        """Create a new topic/queue if it doesn't exist."""
        # Redis Pub/Sub doesn't require explicit topic creation
        logger.debug(f"Topic {topic_name} ready (Redis Pub/Sub)")

    async def delete_topic(self, topic_name: str) -> None:
        """Delete a topic/queue."""
        # Redis Pub/Sub doesn't have persistent topics
        # We can clear dead letter queue for this topic
        pattern = f"{self._dead_letter_prefix}{topic_name}:*"
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

        logger.debug(f"Cleared dead letter queue for topic {topic_name}")

    async def topic_exists(self, topic_name: str) -> bool:
        """Check if a topic/queue exists."""
        # In Redis Pub/Sub, topics always "exist"
        return True

    async def get_dead_letter_events(
        self, topic: Optional[str] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Retrieve events from dead letter queue."""
        events = []

        # Get dead letter keys
        pattern = f"{self._dead_letter_prefix}{topic or '*'}:*"
        cursor = 0
        keys = []

        while True:
            cursor, batch = await self._redis.scan(cursor, match=pattern)
            keys.extend(batch)
            if cursor == 0:
                break

        # Get events from lists
        for key in keys[:max_items] if max_items else keys:
            # Get all events from this dead letter list
            event_jsons = await self._redis.lrange(key, 0, -1)
            for event_json in event_jsons:
                try:
                    event = EventMessage.from_json(event_json)
                    events.append(event)
                except Exception as e:
                    logger.error(f"Failed to parse dead letter event: {e}")

        return events[:max_items] if max_items else events

    async def reprocess_dead_letter_event(
        self, event_id: str, topic: Optional[str] = None
    ) -> None:
        """Reprocess a dead letter event."""
        # Find the event in dead letter queues
        pattern = f"{self._dead_letter_prefix}{topic or '*'}:*"
        cursor = 0

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern)

            for key in keys:
                # Search for the event in this list
                event_jsons = await self._redis.lrange(key, 0, -1)

                for i, event_json in enumerate(event_jsons):
                    try:
                        event = EventMessage.from_json(event_json)
                        if event.id == event_id:
                            # Remove from dead letter queue
                            await self._redis.lrem(key, 1, event_json)

                            # Republish the event
                            await self.publish(event, topic)

                            logger.info(f"Reprocessed dead letter event {event_id}")
                            return
                    except Exception as e:
                        logger.error(f"Error checking dead letter event: {e}")

            if cursor == 0:
                break

        raise ValueError(f"Dead letter event not found: {event_id}")

    def _get_channel_name(self, topic: Optional[str], event_type: str) -> str:
        """Get Redis channel name for topic and event type."""
        if topic:
            return f"lightning:{topic}:{event_type}"
        else:
            return f"lightning:events:{event_type}"

    async def _listen_for_messages(self):
        """Listen for messages from Redis Pub/Sub."""
        logger.info("_listen_for_messages called - Starting Redis Pub/Sub listener")

        try:
            logger.info("Entering Redis listen loop...")
            logger.info(f"Current subscriptions: {list(self._handlers.keys())}")
            logger.info(f"PubSub channels: {self._pubsub.channels}")
            logger.info(f"PubSub patterns: {self._pubsub.patterns}")
            message_count = 0
            async for message in self._pubsub.listen():
                message_count += 1
                logger.debug(f"Redis listener received message #{message_count}: {message.get('type', 'unknown')}")
                if not self._running:
                    break

                if message["type"] in ["message", "pmessage"]:
                    logger.info(f"Received Redis message: type={message['type']}, channel={message.get('channel', 'unknown')}")
                    try:
                        # Parse event
                        event = EventMessage.from_json(message["data"])

                        # Process the event
                        await self._process_event(event, message["channel"])

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        finally:
            logger.info("Redis listener stopped")

    async def _process_event(self, event: EventMessage, channel: str) -> None:
        """Process a single event."""
        # Extract event type from channel
        # Channel format: lightning:topic:event_type or lightning:events:event_type
        parts = channel.split(":")
        if len(parts) >= 3:
            event_type = parts[-1]
        else:
            event_type = event.event_type

        # Find matching subscriptions
        matching_subscriptions = []

        # Direct matches
        if event.event_type in self._handlers:
            matching_subscriptions.extend(self._handlers[event.event_type])

        # Wildcard matches - check all handlers for wildcard patterns
        for handler_pattern, subs in self._handlers.items():
            if "*" in handler_pattern:
                # This is a wildcard subscription pattern
                if handler_pattern == "*" or self._matches_wildcard(event.event_type, handler_pattern):
                    matching_subscriptions.extend(subs)

        # Check if event is orphaned (no matching subscriptions)
        if not matching_subscriptions:
            logger.warning(f"Orphaned event in Redis: {event.event_type} (ID: {event.id})")
            # Store as orphaned event with metadata
            orphaned_key = f"orphaned:{event.event_type}:{event.id}"
            await self._redis.hset(orphaned_key, mapping={
                "event": event.to_json(),
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat()
            })
            await self._redis.expire(orphaned_key, 86400)  # 24 hour TTL
            return

        # Process with each matching handler
        handled = False
        for subscription in matching_subscriptions:
            if self._matches_filter(event, subscription.filter_expression):
                try:
                    await subscription.handler(event)
                    handled = True
                    logger.debug(
                        f"Successfully processed event {event.id} with handler {subscription.subscription_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Handler {subscription.subscription_id} failed for event {event.id}: {e}"
                    )

                    # Add to dead letter queue
                    dead_letter_key = (
                        f"{self._dead_letter_prefix}{event_type}:{event.id}"
                    )
                    await self._redis.lpush(dead_letter_key, event.to_json())
                    await self._redis.expire(dead_letter_key, 86400)  # 24 hour TTL

        # Log if event had subscribers but was filtered out
        if not handled:
            logger.info(f"Event {event.event_type} had subscribers but was filtered out")

    def _matches_wildcard(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches wildcard pattern."""
        if "*" not in pattern:
            return event_type == pattern

        # Convert pattern to regex
        import re

        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
        return bool(re.match(f"^{regex_pattern}$", event_type))

    def _matches_filter(
        self, event: EventMessage, filter_expression: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if event matches filter expression."""
        if not filter_expression:
            return True

        # Simple filter implementation
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

    async def has_subscribers(self, event_type: str, topic: Optional[str] = None) -> bool:
        """Check if an event type has any active subscribers."""
        # Check direct matches
        if event_type in self._handlers and self._handlers[event_type]:
            return True

        # Check wildcard patterns
        for pattern in self._handlers:
            if self._matches_wildcard(event_type, pattern):
                return True

        return False

    async def replay_events(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        topic: Optional[str] = None,
    ) -> List[EventMessage]:
        """
        Replay events from history within a time range.
        
        Note: Redis implementation doesn't support full event history.
        This is a placeholder that returns empty list.
        """
        logger.warning("Event replay not supported in Redis implementation")
        return []

    async def get_event_history(
        self,
        event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventMessage]:
        """
        Get event history by ID or correlation ID.
        
        Note: Redis implementation doesn't support full event history.
        This is a placeholder that returns empty list.
        """
        logger.warning("Event history not supported in Redis implementation")
        return []

    async def get_orphaned_events(
        self, since: Optional[datetime] = None, max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Get events that were published but had no subscribers."""
        events = []
        
        # Scan for orphaned event keys
        pattern = "orphaned:*"
        cursor = 0
        keys = []

        while True:
            cursor, batch = await self._redis.scan(cursor, match=pattern)
            keys.extend(batch)
            if cursor == 0:
                break

        # Get events from Redis
        for key in keys[:max_items] if max_items else keys:
            data = await self._redis.hgetall(key)
            if data and "event" in data:
                try:
                    event = EventMessage.from_json(data["event"])
                    timestamp = datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat()))
                    
                    if since and timestamp < since:
                        continue
                        
                    events.append(event)
                except Exception as e:
                    logger.error(f"Failed to parse orphaned event from {key}: {e}")

        return events[:max_items] if max_items else events

    async def drain_orphaned_events(
        self, event_types: Optional[List[str]] = None, before: Optional[datetime] = None
    ) -> int:
        """Remove orphaned events from the system."""
        count = 0
        
        # Scan for orphaned event keys
        pattern = "orphaned:*"
        cursor = 0

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern)
            
            for key in keys:
                data = await self._redis.hgetall(key)
                if data and "event" in data:
                    try:
                        event = EventMessage.from_json(data["event"])
                        timestamp = datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat()))
                        
                        should_drain = True
                        
                        # Check event type filter
                        if event_types and event.event_type not in event_types:
                            should_drain = False
                            
                        # Check timestamp filter
                        if before and timestamp >= before:
                            should_drain = False
                            
                        if should_drain:
                            await self._redis.delete(key)
                            count += 1
                            logger.info(f"Drained orphaned event: {event.event_type} (ID: {event.id})")
                    except Exception as e:
                        logger.error(f"Error processing orphaned event {key}: {e}")
            
            if cursor == 0:
                break

        return count
