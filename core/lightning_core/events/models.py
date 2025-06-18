"""
Unified event models for both planner and vextir_os
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, constr, ConfigDict

from .types import EventCategory, ScheduleType, ExternalEventType


# Pydantic models for planner schema validation
class PlannerEventModel(BaseModel):
    """Event model for planner schema validation"""
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1, pattern=r"^event\.")
    kind: Optional[ExternalEventType] = None
    schedule: Optional[str] = None
    description: Optional[str] = None


# Dataclass models for runtime events (vextir_os style)
@dataclass
class BaseEvent:
    """Base event class for unified event system"""
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    user_id: Optional[str] = None
    category: EventCategory = EventCategory.INTERNAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ExternalEvent(BaseEvent):
    """External event that can be scheduled/triggered"""
    category: EventCategory = EventCategory.EXTERNAL
    kind: Optional[str] = None
    schedule: Optional[str] = None


@dataclass
class InternalEvent(BaseEvent):
    """Internal system event"""
    category: EventCategory = EventCategory.INTERNAL


# Specific event types (maintaining compatibility with vextir_os)
@dataclass
class VextirEvent(BaseEvent):
    """Base class for vextir_os events (for backward compatibility)"""
    pass


@dataclass
class UserEvent(VextirEvent):
    """Event originating from user interaction"""
    category: EventCategory = EventCategory.INPUT


@dataclass
class SystemEvent(VextirEvent):
    """Internal system event"""
    category: EventCategory = EventCategory.INTERNAL


@dataclass
class OutputEvent(VextirEvent):
    """Event for external output"""
    category: EventCategory = EventCategory.OUTPUT


@dataclass
class EmailEvent(VextirEvent):
    """Email-related event"""
    type: str = "event.email"
    
    
@dataclass
class CalendarEvent(VextirEvent):
    """Calendar-related event"""
    type: str = "event.calendar"


@dataclass
class MessageEvent(VextirEvent):
    """Message-related event"""
    type: str = "event.message"


@dataclass
class WorkerTaskEvent(VextirEvent):
    """Worker task event"""
    type: str = "event.worker.task"


@dataclass
class ContextUpdateEvent(VextirEvent):
    """Context update event"""
    type: str = "event.context.update"


@dataclass
class AuthEvent(VextirEvent):
    """Authentication event"""
    type: str = "event.auth"


@dataclass
class NotificationEvent(VextirEvent):
    """Notification event"""
    type: str = "event.notification"
