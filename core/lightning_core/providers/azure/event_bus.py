"""
Azure Service Bus event bus implementation.
"""

import os
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from collections import defaultdict
import uuid

from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver
from azure.servicebus import ServiceBusMessage, ServiceBusMessageBatch
from azure.servicebus.exceptions import ServiceBusError, MessageNotFoundError
from azure.identity.aio import DefaultAzureCredential

from lightning_core.abstractions.event_bus import (
    EventBus, EventMessage, EventHandler, EventSubscription
)


logger = logging.getLogger(__name__)


class ServiceBusEventBus(EventBus):
    """Azure Service Bus event bus implementation."""
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        fully_qualified_namespace: Optional[str] = None,
        credential: Optional[Any] = None,
        **kwargs: Any
    ):
        # Initialize Service Bus client
        if connection_string:
            self._client = ServiceBusClient.from_connection_string(
                connection_string,
                logging_enable=kwargs.get("logging_enable", False)
            )
        elif fully_qualified_namespace:
            # Use DefaultAzureCredential if no credential provided
            if not credential:
                credential = DefaultAzureCredential()
            self._client = ServiceBusClient(
                fully_qualified_namespace=fully_qualified_namespace,
                credential=credential,
                logging_enable=kwargs.get("logging_enable", False)
            )
        else:
            # Try to get from environment
            conn_str = os.getenv("SERVICE_BUS_CONNECTION_STRING")
            if conn_str:
                self._client = ServiceBusClient.from_connection_string(
                    conn_str,
                    logging_enable=kwargs.get("logging_enable", False)
                )
            else:
                raise ValueError("Service Bus connection string or namespace required")
        
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._receivers: Dict[str, ServiceBusReceiver] = {}
        self._handlers: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._tasks: Set[asyncio.Task] = set()
        self._running = False
        self._max_message_count = kwargs.get("max_message_count", 10)
        self._max_wait_time = kwargs.get("max_wait_time", 5)
    
    async def publish(
        self,
        event: EventMessage,
        topic: Optional[str] = None
    ) -> None:
        """Publish an event to the event bus."""
        queue_name = topic or "default-queue"
        
        async with self._client.get_queue_sender(queue_name) as sender:
            # Convert event to Service Bus message
            message = ServiceBusMessage(
                body=event.to_json(),
                subject=event.event_type,
                message_id=event.id,
                correlation_id=event.correlation_id,
                reply_to=event.reply_to,
                time_to_live=event.ttl_seconds
            )
            
            # Add metadata as application properties
            for key, value in event.metadata.items():
                message.application_properties[key] = value
            
            await sender.send_messages(message)
            logger.debug(f"Published event {event.id} to queue {queue_name}")
    
    async def publish_batch(
        self,
        events: List[EventMessage],
        topic: Optional[str] = None
    ) -> None:
        """Publish multiple events as a batch."""
        queue_name = topic or "default-queue"
        
        async with self._client.get_queue_sender(queue_name) as sender:
            # Create message batch
            async with sender.create_message_batch() as batch:
                for event in events:
                    message = ServiceBusMessage(
                        body=event.to_json(),
                        subject=event.event_type,
                        message_id=event.id,
                        correlation_id=event.correlation_id,
                        reply_to=event.reply_to,
                        time_to_live=event.ttl_seconds
                    )
                    
                    # Add metadata
                    for key, value in event.metadata.items():
                        message.application_properties[key] = value
                    
                    try:
                        batch.add_message(message)
                    except ValueError:
                        # Batch is full, send it and create a new one
                        await sender.send_messages(batch)
                        batch = await sender.create_message_batch()
                        batch.add_message(message)
                
                # Send remaining messages
                if batch.size_in_bytes > 0:
                    await sender.send_messages(batch)
            
            logger.debug(f"Published {len(events)} events to queue {queue_name}")
    
    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        topic: Optional[str] = None,
        filter_expression: Optional[Dict[str, Any]] = None
    ) -> str:
        """Subscribe to events of a specific type."""
        subscription_id = str(uuid.uuid4())
        queue_name = topic or "default-queue"
        
        subscription = EventSubscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler=handler,
            filter_expression=filter_expression
        )
        
        self._subscriptions[subscription_id] = subscription
        self._handlers[event_type].append(subscription)
        
        # Ensure queue exists and start processing if not already
        if queue_name not in self._receivers and self._running:
            await self._start_queue_processor(queue_name)
        
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
        
        # Start processors for all queues with subscriptions
        queues = set()
        for subscription in self._subscriptions.values():
            # For Service Bus, we need to know which queues to monitor
            # This is a simplification - in production you'd track queue per subscription
            queues.add("default-queue")
        
        for queue in queues:
            await self._start_queue_processor(queue)
        
        logger.info("Azure Service Bus event bus started")
    
    async def stop(self) -> None:
        """Stop the event bus (stop processing events)."""
        self._running = False
        
        # Close all receivers
        for receiver in self._receivers.values():
            await receiver.close()
        self._receivers.clear()
        
        # Cancel all processing tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Close client
        await self._client.close()
        
        logger.info("Azure Service Bus event bus stopped")
    
    async def create_topic(self, topic_name: str) -> None:
        """Create a new topic/queue if it doesn't exist."""
        # Note: Creating queues requires management plane access
        # This is typically done through ARM templates or Azure Portal
        # For now, we assume queues are pre-created
        logger.warning(f"Queue creation not implemented. Ensure {topic_name} exists in Service Bus namespace")
    
    async def delete_topic(self, topic_name: str) -> None:
        """Delete a topic/queue."""
        # Note: Deleting queues requires management plane access
        logger.warning(f"Queue deletion not implemented. Delete {topic_name} through Azure Portal")
    
    async def topic_exists(self, topic_name: str) -> bool:
        """Check if a topic/queue exists."""
        try:
            # Try to create a receiver to check if queue exists
            receiver = self._client.get_queue_receiver(topic_name)
            await receiver.close()
            return True
        except ServiceBusError:
            return False
    
    async def get_dead_letter_events(
        self,
        topic: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[EventMessage]:
        """Retrieve events from dead letter queue."""
        queue_name = topic or "default-queue"
        dead_letter_queue = f"{queue_name}/$deadletterqueue"
        
        events = []
        
        async with self._client.get_queue_receiver(
            queue_name=dead_letter_queue,
            max_message_count=max_items or self._max_message_count
        ) as receiver:
            messages = await receiver.receive_messages(
                max_message_count=max_items or self._max_message_count,
                max_wait_time=self._max_wait_time
            )
            
            for message in messages:
                try:
                    event = EventMessage.from_json(str(message))
                    events.append(event)
                except Exception as e:
                    logger.error(f"Failed to parse dead letter message: {e}")
        
        return events
    
    async def reprocess_dead_letter_event(
        self,
        event_id: str,
        topic: Optional[str] = None
    ) -> None:
        """Reprocess a dead letter event."""
        queue_name = topic or "default-queue"
        dead_letter_queue = f"{queue_name}/$deadletterqueue"
        
        async with self._client.get_queue_receiver(
            queue_name=dead_letter_queue,
            max_message_count=100
        ) as receiver:
            # Find the message
            messages = await receiver.receive_messages(
                max_message_count=100,
                max_wait_time=self._max_wait_time
            )
            
            for message in messages:
                if message.message_id == event_id:
                    # Parse event
                    event = EventMessage.from_json(str(message))
                    
                    # Complete the dead letter message
                    await receiver.complete_message(message)
                    
                    # Republish to main queue
                    await self.publish(event, topic)
                    
                    logger.info(f"Reprocessed dead letter event {event_id}")
                    return
        
        raise ValueError(f"Dead letter event not found: {event_id}")
    
    async def _start_queue_processor(self, queue_name: str) -> None:
        """Start processing messages from a queue."""
        if queue_name not in self._receivers:
            self._receivers[queue_name] = self._client.get_queue_receiver(
                queue_name=queue_name,
                max_message_count=self._max_message_count
            )
            
            task = asyncio.create_task(self._process_queue(queue_name))
            self._tasks.add(task)
    
    async def _process_queue(self, queue_name: str) -> None:
        """Process messages from a specific queue."""
        logger.info(f"Started processing queue: {queue_name}")
        receiver = self._receivers[queue_name]
        
        while self._running:
            try:
                messages = await receiver.receive_messages(
                    max_message_count=self._max_message_count,
                    max_wait_time=self._max_wait_time
                )
                
                for message in messages:
                    try:
                        # Parse event
                        event = EventMessage.from_json(str(message))
                        
                        # Process the event
                        await self._process_event(event, message, receiver)
                        
                    except Exception as e:
                        logger.error(f"Failed to process message: {e}")
                        # Dead letter the message
                        await receiver.dead_letter_message(
                            message,
                            reason="ProcessingError",
                            error_description=str(e)
                        )
                
            except ServiceBusError as e:
                logger.error(f"Service Bus error in queue {queue_name}: {e}")
                await asyncio.sleep(5)  # Back off on error
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error processing queue {queue_name}: {e}")
                await asyncio.sleep(5)
        
        logger.info(f"Stopped processing queue: {queue_name}")
    
    async def _process_event(
        self,
        event: EventMessage,
        message: ServiceBusMessage,
        receiver: ServiceBusReceiver
    ) -> None:
        """Process a single event."""
        # Find matching subscriptions
        matching_subscriptions = []
        
        # Direct event type matches
        if event.event_type in self._handlers:
            matching_subscriptions.extend(self._handlers[event.event_type])
        
        # Wildcard matches
        for pattern, subscriptions in self._handlers.items():
            if "*" in pattern:
                import re
                regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
                if re.match(f"^{regex_pattern}$", event.event_type):
                    matching_subscriptions.extend(subscriptions)
        
        # Process with each matching handler
        success = True
        for subscription in matching_subscriptions:
            if self._matches_filter(event, subscription.filter_expression):
                try:
                    await subscription.handler(event)
                except Exception as e:
                    logger.error(f"Handler {subscription.subscription_id} failed: {e}")
                    success = False
        
        # Complete or abandon message based on processing result
        if success:
            await receiver.complete_message(message)
        else:
            await receiver.abandon_message(message)
    
    def _matches_filter(
        self,
        event: EventMessage,
        filter_expression: Optional[Dict[str, Any]]
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