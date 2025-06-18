"""
Event type definitions and enums
"""

from enum import Enum
from typing import Literal


class EventCategory(Enum):
    """Event categories for classification"""
    INPUT = "input"      # From external world (user input, sensors, APIs)
    INTERNAL = "internal"  # System communication between components
    OUTPUT = "output"    # To external world (UI updates, notifications)
    EXTERNAL = "external"  # External scheduled/triggered events (for planner)


class ScheduleType(Enum):
    """Types of event scheduling"""
    CRON = "time.cron"
    INTERVAL = "time.interval"
    WEBHOOK = "webhook"
    MANUAL = "manual"


# Type aliases for compatibility
EventType = Literal[
    "event.email",
    "event.calendar", 
    "event.message",
    "event.worker.task",
    "event.context.update",
    "event.auth",
    "event.notification",
    "event.system.start",
    "event.system.stop",
    "event.user.action"
]

ExternalEventType = Literal["time.cron", "time.interval", "webhook", "manual"]
