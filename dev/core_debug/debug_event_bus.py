#!/usr/bin/env python3
"""
Debug Event Bus - Find out why events aren't being processed
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
import os

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Load .env
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage


async def debug_event_bus():
    """Debug the event bus to find issues."""
    
    print("EVENT BUS DEBUG")
    print("="*50)
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/debug",
        event_bus_provider="local"
    )
    
    print("1. Initializing runtime...")
    runtime = await initialize_runtime(config)
    print(f"   Runtime initialized: {runtime}")
    print(f"   Event bus type: {type(runtime.event_bus)}")
    print(f"   Event bus running: {getattr(runtime.event_bus, '_running', 'unknown')}")
    
    # Test 1: Simple publish/subscribe
    print("\n2. Testing simple publish/subscribe...")
    
    received_events = []
    
    async def test_handler(event: EventMessage):
        print(f"   [Handler] Received: {event.event_type}")
        received_events.append(event)
    
    # Subscribe
    sub_id = await runtime.event_bus.subscribe("test.event", test_handler)
    print(f"   Subscribed with ID: {sub_id}")
    
    # Publish
    test_event = EventMessage(
        event_type="test.event",
        data={"message": "Hello"}
    )
    print(f"   Publishing event: {test_event.event_type}")
    await runtime.event_bus.publish(test_event)
    
    # Wait a bit
    print("   Waiting 2 seconds...")
    await asyncio.sleep(2)
    
    print(f"   Received {len(received_events)} events")
    
    # Test 2: Check event bus internals
    print("\n3. Checking event bus internals...")
    if hasattr(runtime.event_bus, '_topics'):
        print(f"   Topics: {list(runtime.event_bus._topics.keys())}")
        for topic, queue in runtime.event_bus._topics.items():
            print(f"   Topic '{topic}' queue size: {queue.qsize()}")
    
    if hasattr(runtime.event_bus, '_handlers'):
        print(f"   Handlers: {list(runtime.event_bus._handlers.keys())}")
        for event_type, subs in runtime.event_bus._handlers.items():
            print(f"   Event type '{event_type}' has {len(subs)} subscribers")
    
    if hasattr(runtime.event_bus, '_tasks'):
        print(f"   Active tasks: {len(runtime.event_bus._tasks)}")
        for task in runtime.event_bus._tasks:
            print(f"     Task: {task}, done: {task.done()}, cancelled: {task.cancelled()}")
    
    # Test 3: Manual event processing
    print("\n4. Testing manual event processing...")
    
    # Try wildcard subscription
    async def wildcard_handler(event: EventMessage):
        print(f"   [Wildcard] Got: {event.event_type}")
    
    await runtime.event_bus.subscribe("*", wildcard_handler)
    
    # Send another event
    await runtime.event_bus.publish(EventMessage(
        event_type="another.test",
        data={"test": True}
    ))
    
    await asyncio.sleep(1)
    
    # Check if we need to manually process
    if hasattr(runtime.event_bus, '_process_event'):
        print("\n5. Trying manual event processing...")
        if hasattr(runtime.event_bus, '_topics') and 'default' in runtime.event_bus._topics:
            queue = runtime.event_bus._topics['default']
            if not queue.empty():
                event = await queue.get()
                print(f"   Got event from queue: {event.event_type}")
                await runtime.event_bus._process_event(event, 'default')
    
    print("\n6. Summary:")
    print(f"   Events received by handlers: {len(received_events)}")
    print(f"   Event bus is running: {getattr(runtime.event_bus, '_running', False)}")
    
    # Cleanup
    await runtime.shutdown()
    print("\n✓ Debug complete")


if __name__ == "__main__":
    asyncio.run(debug_event_bus())