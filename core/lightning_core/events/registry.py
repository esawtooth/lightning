"""
Unified event registry for both planner and vextir_os
"""

from dataclasses import dataclass
from typing import Dict, Optional, Set, List
from .types import EventCategory, ScheduleType, ExternalEventType


@dataclass
class EventDefinition:
    """Definition of an event type"""
    name: str
    category: EventCategory
    description: Optional[str] = None
    kind: Optional[str] = None  # For external events (cron, webhook, etc.)
    schedule_pattern: Optional[str] = None  # Cron pattern or interval
    required_data: Optional[List[str]] = None  # Required data fields
    metadata: Optional[Dict] = None


class EventRegistry:
    """Unified registry for all event types"""
    
    _events: Dict[str, EventDefinition] = {}
    
    @classmethod
    def register(cls, event_def: EventDefinition) -> None:
        """Register an event definition"""
        cls._events[event_def.name] = event_def
    
    @classmethod
    def get(cls, name: str) -> Optional[EventDefinition]:
        """Get event definition by name"""
        return cls._events.get(name)
    
    @classmethod
    def get_all(cls) -> Dict[str, EventDefinition]:
        """Get all registered events"""
        return cls._events.copy()
    
    @classmethod
    def get_by_category(cls, category: EventCategory) -> Dict[str, EventDefinition]:
        """Get events by category"""
        return {
            name: event_def 
            for name, event_def in cls._events.items() 
            if event_def.category == category
        }
    
    @classmethod
    def get_external_events(cls) -> Dict[str, EventDefinition]:
        """Get external events (for planner)"""
        return cls.get_by_category(EventCategory.EXTERNAL)
    
    @classmethod
    def is_external(cls, name: str) -> bool:
        """Check if event is external"""
        event_def = cls.get(name)
        return event_def is not None and event_def.category == EventCategory.EXTERNAL
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered events (for testing)"""
        cls._events.clear()


# Register default events
def _register_default_events():
    """Register default event definitions"""
    
    # External events (for planner)
    EventRegistry.register(EventDefinition(
        name="event.email.check",
        category=EventCategory.EXTERNAL,
        kind="time.interval",
        description="Check for new emails",
        schedule_pattern="PT5M",  # Every 5 minutes
        required_data=["folder"]
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.calendar.sync",
        category=EventCategory.EXTERNAL,
        kind="time.cron",
        description="Sync calendar events",
        schedule_pattern="0 */6 * * *",  # Every 6 hours
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.webhook.github",
        category=EventCategory.EXTERNAL,
        kind="webhook",
        description="GitHub webhook events",
        required_data=["repository", "action"]
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.manual.trigger",
        category=EventCategory.EXTERNAL,
        kind="manual",
        description="Manually triggered event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.time.daily",
        category=EventCategory.EXTERNAL,
        kind="time.cron",
        description="Daily time-based trigger",
        schedule_pattern="0 20 * * *",  # Default to 8 PM, can be customized
    ))
    
    # Internal events (for vextir_os)
    EventRegistry.register(EventDefinition(
        name="event.email",
        category=EventCategory.INTERNAL,
        description="Email processing event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.calendar",
        category=EventCategory.INTERNAL,
        description="Calendar event processing"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.message",
        category=EventCategory.INTERNAL,
        description="Message processing event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.worker.task",
        category=EventCategory.INTERNAL,
        description="Worker task event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.context.update",
        category=EventCategory.INTERNAL,
        description="Context update event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.auth",
        category=EventCategory.INTERNAL,
        description="Authentication event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.notification",
        category=EventCategory.OUTPUT,
        description="Notification output event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.system.start",
        category=EventCategory.INTERNAL,
        description="System startup event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.system.stop",
        category=EventCategory.INTERNAL,
        description="System shutdown event"
    ))
    
    EventRegistry.register(EventDefinition(
        name="event.user.action",
        category=EventCategory.INPUT,
        description="User action event"
    ))


# Initialize default events
_register_default_events()


# Legacy compatibility - provide dict-like interface for planner
class LegacyEventRegistry:
    """Legacy interface for backward compatibility with planner"""
    
    @staticmethod
    def __contains__(name: str) -> bool:
        return EventRegistry.get(name) is not None
    
    @staticmethod
    def __getitem__(name: str) -> Dict:
        event_def = EventRegistry.get(name)
        if event_def is None:
            raise KeyError(f"Event {name} not found")
        
        return {
            "kind": event_def.kind,
            "description": event_def.description,
            "schedule": event_def.schedule_pattern
        }
    
    @staticmethod
    def __iter__():
        return iter(EventRegistry.get_all().keys())
    
    @staticmethod
    def keys():
        return EventRegistry.get_all().keys()
    
    @staticmethod
    def items():
        legacy_registry = LegacyEventRegistry()
        return [(name, legacy_registry[name]) for name in legacy_registry.keys()]


# Create legacy instance for backward compatibility
LegacyEventRegistryInstance = LegacyEventRegistry()
