#!/usr/bin/env python3
"""
Basic usage examples for Lightning Core library
"""

import asyncio
import json
from lightning_core.vextir_os import (
    Event, EventBus, EventFilter, 
    Driver, DriverManifest, DriverType, ResourceSpec,
    get_event_bus, get_driver_registry
)
from lightning_core.planner.schema import PlanModel, StepModel, ExternalEventModel


async def demo_event_system():
    """Demonstrate the event system"""
    print("=== Event System Demo ===")
    
    # Get the global event bus
    bus = get_event_bus()
    
    # Create some events
    user_event = Event(
        type="user.login",
        data={"user_id": "alice", "timestamp": "2023-01-01T10:00:00Z"},
        source="web-app"
    )
    
    system_event = Event(
        type="system.startup",
        data={"version": "1.0.0", "components": ["api", "ui", "worker"]},
        source="system"
    )
    
    # Subscribe to events
    received_events = []
    
    def event_handler(event):
        received_events.append(event)
        print(f"Received event: {event.type} from {event.source}")
    
    # Subscribe to user events only
    user_filter = EventFilter(event_types=["user.login", "user.logout"])
    subscription_id = bus.subscribe(user_filter, event_handler)
    
    # Emit events
    await bus.emit(user_event)
    await bus.emit(system_event)
    
    print(f"Events received by handler: {len(received_events)}")
    print(f"Event types: {[e.type for e in received_events]}")
    
    # Get event history
    history = await bus.get_history(limit=10)
    print(f"Total events in history: {len(history)}")
    
    # Cleanup
    bus.unsubscribe(subscription_id)
    print()


class ExampleDriver(Driver):
    """Example custom driver"""
    
    def get_capabilities(self):
        return ["example.process", "example.transform"]
    
    def get_resource_requirements(self):
        return ResourceSpec(memory_mb=128, timeout_seconds=10)
    
    async def handle_event(self, event):
        print(f"ExampleDriver processing: {event.type}")
        
        if event.type == "example.process":
            # Simulate processing
            result = {"processed": True, "input": event.data}
            return [Event(
                type="example.completed",
                data=result,
                source="example-driver"
            )]
        
        return []


async def demo_driver_system():
    """Demonstrate the driver system"""
    print("=== Driver System Demo ===")
    
    # Create driver manifest
    manifest = DriverManifest(
        id="example-driver",
        name="Example Driver",
        version="1.0.0",
        author="Demo",
        description="An example driver for demonstration",
        driver_type=DriverType.TOOL,
        capabilities=["example.process", "example.transform"],
        resource_requirements=ResourceSpec(memory_mb=128)
    )
    
    # Register the driver
    registry = get_driver_registry()
    await registry.register_driver(manifest, ExampleDriver)
    
    # Create an event that the driver can handle
    process_event = Event(
        type="example.process",
        data={"input": "Hello, World!", "operation": "uppercase"},
        source="demo"
    )
    
    # Route event through the driver system
    result_events = await registry.route_event(process_event)
    
    print(f"Driver produced {len(result_events)} result events")
    for event in result_events:
        print(f"  - {event.type}: {event.data}")
    
    # List all drivers
    drivers = registry.list_drivers()
    print(f"Registered drivers: {len(drivers)}")
    for driver_info in drivers:
        print(f"  - {driver_info['name']} ({driver_info['type']}): {driver_info['capabilities']}")
    
    print()


def demo_planner_schema():
    """Demonstrate the planner schema"""
    print("=== Planner Schema Demo ===")
    
    # Create a simple plan
    events = [
        ExternalEventModel(
            name="event.daily_check",
            kind="time.cron",
            schedule="0 9 * * *",
            description="Daily morning check"
        )
    ]
    
    steps = [
        StepModel(
            name="fetch_data",
            on=["event.daily_check"],
            action="data.fetch",
            args={"source": "api", "format": "json"},
            emits=["event.data_ready"]
        ),
        StepModel(
            name="process_data",
            on=["event.data_ready"],
            action="data.process",
            args={"algorithm": "summarize"},
            emits=["event.processing_complete"]
        ),
        StepModel(
            name="send_report",
            on=["event.processing_complete"],
            action="email.send",
            args={"to": "admin@example.com", "subject": "Daily Report"}
        )
    ]
    
    plan = PlanModel(
        plan_name="daily_data_processing",
        graph_type="acyclic",
        events=events,
        steps=steps
    )
    
    print(f"Created plan: {plan.plan_name}")
    print(f"Graph type: {plan.graph_type}")
    print(f"External events: {len(plan.events)}")
    print(f"Processing steps: {len(plan.steps)}")
    
    # Convert to JSON
    plan_json = plan.model_dump()
    print(f"Plan JSON size: {len(json.dumps(plan_json))} characters")
    
    # Show the plan structure
    print("\nPlan structure:")
    for i, step in enumerate(plan.steps, 1):
        triggers = ", ".join(step.on)
        emits = ", ".join(step.emits) if step.emits else "none"
        print(f"  {i}. {step.name}")
        print(f"     Triggers on: {triggers}")
        print(f"     Action: {step.action}")
        print(f"     Emits: {emits}")
    
    print()


async def demo_event_streaming():
    """Demonstrate event streaming"""
    print("=== Event Streaming Demo ===")
    
    bus = get_event_bus()
    
    # Create a filter for user events
    user_filter = EventFilter(event_types=["user.action"])
    
    # Use event stream in a context manager
    async def stream_processor():
        from lightning_core.vextir_os.event_bus import EventStream
        
        async with EventStream(user_filter, bus) as stream:
            print("Waiting for user events...")
            
            # This would normally run in a loop, but for demo we'll just get one
            try:
                event = await asyncio.wait_for(stream.get_event(), timeout=2.0)
                print(f"Streamed event: {event.type} - {event.data}")
            except asyncio.TimeoutError:
                print("No events received within timeout")
    
    # Start the stream processor
    stream_task = asyncio.create_task(stream_processor())
    
    # Give it a moment to start
    await asyncio.sleep(0.1)
    
    # Emit a user event
    await bus.emit(Event(
        type="user.action",
        data={"action": "click", "element": "button"},
        source="web-ui"
    ))
    
    # Wait for the stream processor to complete
    await stream_task
    
    print()


async def main():
    """Run all demos"""
    print("Lightning Core Library Demo")
    print("=" * 40)
    
    await demo_event_system()
    await demo_driver_system()
    demo_planner_schema()
    await demo_event_streaming()
    
    print("Demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
