"""
Lightning Core - AI Planning and Operating System Library

This library provides two main components:
1. Lightning Planner - Workflow planning and validation system
2. Vextir OS - Event-driven AI operating system

Example usage:

    # Planning
    from lightning_core.planner import create_verified_plan, PlanModel
    
    plan = create_verified_plan("Send daily email summaries")
    
    # Event System
    from lightning_core.vextir_os import EventBus, Event
    
    bus = EventBus()
    await bus.emit(Event(type="user.message", data={"text": "Hello"}))
"""

__version__ = "0.1.0"
__author__ = "Lightning Team"
__email__ = "team@lightning.ai"

# Import main components for easy access
from lightning_core.planner import (
    PlanModel,
    create_verified_plan,
    validate_plan,
    PlanValidationError,
    ToolRegistry,
    PlanStore,
)

from lightning_core.vextir_os import (
    EventBus,
    Event,
    Driver,
    DriverRegistry,
    get_event_bus,
    emit_event,
)

__all__ = [
    # Version info
    "__version__",
    "__author__", 
    "__email__",
    
    # Planner components
    "PlanModel",
    "create_verified_plan",
    "validate_plan",
    "PlanValidationError",
    "ToolRegistry",
    "PlanStore",
    
    # Vextir OS components
    "EventBus",
    "Event",
    "Driver",
    "DriverRegistry",
    "get_event_bus",
    "emit_event",
]
