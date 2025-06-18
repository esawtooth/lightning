"""
Vextir OS Event Bus - Core message passing system
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .events import Event, EventCategory


@dataclass
class EventFilter:
    """Filter for event subscriptions"""

    event_types: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None
    categories: Optional[List[EventCategory]] = None

    def matches(self, event: Event) -> bool:
        """Check if event matches this filter"""
        if self.event_types and event.type not in self.event_types:
            return False
        if self.sources and event.source not in self.sources:
            return False
        if self.user_ids and event.user_id not in self.user_ids:
            return False
        if self.categories:
            event_category = getattr(event, "category", EventCategory.INTERNAL)
            if event_category not in self.categories:
                return False
        return True


@dataclass
class EventSubscription:
    """Event subscription with callback"""

    id: str
    filter: EventFilter
    callback: Callable[[Event], None]
    active: bool = True


class EventStream:
    """Stream of events matching a filter"""

    def __init__(self, filter: EventFilter, bus: "EventBus"):
        self.filter = filter
        self.bus = bus
        self.queue = asyncio.Queue()
        self.subscription_id = str(uuid.uuid4())

    async def __aenter__(self):
        self.bus.subscribe_stream(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.bus.unsubscribe_stream(self.subscription_id)

    async def get_event(self) -> Event:
        """Get next event from stream"""
        return await self.queue.get()

    def put_event(self, event: Event):
        """Put event into stream (called by bus)"""
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logging.warning(f"Event stream queue full, dropping event {event.id}")


class EventBus:
    """Core event bus for Vextir OS"""

    def __init__(self):
        self.subscriptions: Dict[str, EventSubscription] = {}
        self.streams: Dict[str, EventStream] = {}
        self.event_history: List[Event] = []
        self.max_history = 10000
        self._lock = asyncio.Lock()

    async def emit(self, event: Event) -> str:
        """Queue event for processing and return event ID"""
        if not event.id:
            event.id = str(uuid.uuid4())

        # Add to history
        async with self._lock:
            self.event_history.append(event)
            if len(self.event_history) > self.max_history:
                self.event_history.pop(0)

        # Notify subscribers
        await self._notify_subscribers(event)

        logging.info(f"Event emitted: {event.type} (ID: {event.id})")
        return event.id

    def subscribe(self, filter: EventFilter, callback: Callable[[Event], None]) -> str:
        """Subscribe to event stream with callback"""
        subscription_id = str(uuid.uuid4())
        subscription = EventSubscription(
            id=subscription_id, filter=filter, callback=callback
        )
        self.subscriptions[subscription_id] = subscription
        return subscription_id

    def unsubscribe(self, subscription_id: str):
        """Unsubscribe from events"""
        if subscription_id in self.subscriptions:
            del self.subscriptions[subscription_id]

    def subscribe_stream(self, stream: EventStream):
        """Subscribe an event stream"""
        self.streams[stream.subscription_id] = stream

    def unsubscribe_stream(self, subscription_id: str):
        """Unsubscribe an event stream"""
        if subscription_id in self.streams:
            del self.streams[subscription_id]

    async def _notify_subscribers(self, event: Event):
        """Notify all matching subscribers"""
        # Notify callback subscribers
        for subscription in self.subscriptions.values():
            if subscription.active and subscription.filter.matches(event):
                try:
                    subscription.callback(event)
                except Exception as e:
                    logging.error(f"Error in event callback: {e}")

        # Notify stream subscribers
        for stream in self.streams.values():
            if stream.filter.matches(event):
                stream.put_event(event)

    async def get_history(
        self, filter: Optional[EventFilter] = None, limit: int = 100
    ) -> List[Event]:
        """Get event history with optional filtering"""
        async with self._lock:
            events = self.event_history.copy()

        if filter:
            events = [e for e in events if filter.matches(e)]

        return events[-limit:]


# Global event bus instance
_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get global event bus instance"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


async def emit_event(event: Event) -> str:
    """Convenience function to emit event to global bus"""
    bus = get_event_bus()
    return await bus.emit(event)


def subscribe_to_events(filter: EventFilter, callback: Callable[[Event], None]) -> str:
    """Convenience function to subscribe to global bus"""
    bus = get_event_bus()
    return bus.subscribe(filter, callback)
