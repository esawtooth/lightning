"""
Vextir OS - Core AI Operating System Components
"""

__version__ = "0.1.0"

from .drivers import (
    AgentDriver,
    Driver,
    DriverManifest,
    DriverRegistry,
    DriverType,
    IODriver,
    ResourceSpec,
    ToolDriver,
    UIDriver,
    driver,
    get_driver_registry,
)
from .event_bus import (
    EventBus,
    EventFilter,
    EventStream,
    EventSubscription,
    emit_event,
    get_event_bus,
    subscribe_to_events,
)

# Import main components for easy access
from .events import (
    AuthEvent,
    CalendarEvent,
    ContextUpdateEvent,
    EmailEvent,
    Event,
    EventCategory,
    MessageEvent,
    NotificationEvent,
    OutputEvent,
    SystemEvent,
    UserEvent,
    WorkerTaskEvent,
)
from .universal_processor import (
    EventProcessingError,
    UniversalEventProcessor,
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
