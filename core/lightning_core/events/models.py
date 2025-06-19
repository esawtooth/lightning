"""
Unified event models for both planner and vextir_os
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, constr

from .types import EventCategory, ExternalEventType, ScheduleType


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
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent":
        """Create event from dictionary."""
        # Get valid field names for this class
        import inspect
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        
        # Filter data to only include valid fields
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        # Handle timestamp conversion
        if 'timestamp' in filtered_data and isinstance(filtered_data['timestamp'], str):
            filtered_data['timestamp'] = datetime.fromisoformat(filtered_data['timestamp'].replace('Z', '+00:00'))
        
        # Handle category conversion
        if 'category' in filtered_data and isinstance(filtered_data['category'], str):
            filtered_data['category'] = EventCategory(filtered_data['category'])
            
        return cls(**filtered_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        result = {
            'id': self.id,
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'source': self.source,
            'user_id': self.user_id,
            'category': self.category.value if hasattr(self.category, 'value') else self.category,
            'metadata': self.metadata
        }
        return {k: v for k, v in result.items() if v is not None}


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

    type: str = "email"


@dataclass
class CalendarEvent(VextirEvent):
    """Calendar-related event"""

    type: str = "calendar"


@dataclass
class MessageEvent(VextirEvent):
    """Message-related event"""

    type: str = "message"


@dataclass
class WorkerTaskEvent(VextirEvent):
    """Worker task event"""

    type: str = "worker.task"


@dataclass
class ContextUpdateEvent(VextirEvent):
    """Context update event"""

    type: str = "context.update"


@dataclass
class AuthEvent(VextirEvent):
    """Authentication event"""

    type: str = "auth"


@dataclass
class NotificationEvent(VextirEvent):
    """Notification event"""

    type: str = "notification"


@dataclass
class LLMChatEvent(VextirEvent):
    """LLM Chat event"""

    type: str = "llm.chat"


@dataclass
class VoiceCallEvent(VextirEvent):
    """Voice call event"""

    type: str = "voice.call"


@dataclass
class InstructionEvent(VextirEvent):
    """Instruction event"""

    type: str = "instruction"


# Backward compatibility alias
Event = VextirEvent
