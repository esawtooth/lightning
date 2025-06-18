"""
Vextir OS Event System - Core event definitions
Now using unified event system
"""

# Import from unified event system
from ..events.models import (
    AuthEvent,
)
from ..events.models import BaseEvent as Event
from ..events.models import (
    CalendarEvent,
    ContextUpdateEvent,
    EmailEvent,
    MessageEvent,
    NotificationEvent,
    OutputEvent,
    SystemEvent,
    UserEvent,
    VextirEvent,
    WorkerTaskEvent,
)
from ..events.types import EventCategory

# Re-export for backward compatibility
__all__ = [
    "Event",
    "EventCategory",
    "VextirEvent",
    "UserEvent",
    "SystemEvent",
    "OutputEvent",
    "EmailEvent",
    "CalendarEvent",
    "MessageEvent",
    "WorkerTaskEvent",
    "ContextUpdateEvent",
    "AuthEvent",
    "NotificationEvent",
]
