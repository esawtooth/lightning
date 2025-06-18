"""
Vextir OS - Core AI Operating System Components
"""

__version__ = "0.1.0"

# Import main components for easy access
from .events import (
    Event,
    EventCategory,
    UserEvent,
    SystemEvent,
    OutputEvent,
    EmailEvent,
    CalendarEvent,
    MessageEvent,
    WorkerTaskEvent,
    ContextUpdateEvent,
    AuthEvent,
    NotificationEvent,
)

from .event_bus import (
    EventBus,
    EventFilter,
    EventStream,
    EventSubscription,
    get_event_bus,
    emit_event,
    subscribe_to_events,
)

from .drivers import (
    Driver,
    AgentDriver,
    ToolDriver,
    IODriver,
    UIDriver,
    DriverRegistry,
    DriverManifest,
    DriverType,
    ResourceSpec,
    get_driver_registry,
    driver,
)

from .universal_processor import (
    UniversalEventProcessor,
    EventProcessingError,
    get_universal_processor,
    process_event_message,
)

__all__ = [
    # Events
    "Event",
    "EventCategory", 
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
    
    # Event Bus
    "EventBus",
    "EventFilter",
    "EventStream", 
    "EventSubscription",
    "get_event_bus",
    "emit_event",
    "subscribe_to_events",
    
    # Drivers
    "Driver",
    "AgentDriver",
    "ToolDriver",
    "IODriver",
    "UIDriver",
    "DriverRegistry",
    "DriverManifest",
    "DriverType",
    "ResourceSpec",
    "get_driver_registry",
    "driver",
    
    # Processing
    "UniversalEventProcessor",
    "EventProcessingError",
    "get_universal_processor",
    "process_event_message",
]
