#!/usr/bin/env python3
"""
Quick script to run the universal event processor locally.

This demonstrates how developers can test the event processing
logic on their local machine without any Azure dependencies.
"""

import asyncio
import logging
from datetime import datetime

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage, FunctionConfig
from lightning_core.abstractions.serverless import RuntimeType
from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def run_local_event_processor():
    """Run the event processor locally with minimal setup."""
    
    print("🚀 Starting Local Event Processor")
    print("=" * 50)
    
    # Configure for local environment
    configure_drivers_for_environment()
    
    # Initialize only required drivers for faster startup
    print("Initializing drivers...")
    await initialize_required_drivers()
    
    # Create local runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/local_processor",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Runtime initialized")
    
    # Deploy the processor function
    print("\nDeploying event processor function...")
    function_config = FunctionConfig(
        name="event-processor",
        handler="universal_event_processor_handler",
        runtime=RuntimeType.PYTHON,
        memory_mb=256,
        timeout_seconds=60
    )
    function_id = await runtime.serverless.deploy_function(
        config=function_config,
        handler=universal_event_processor_handler
    )
    print(f"✓ Function deployed: {function_id}")
    
    # Set up event routing
    async def route_events(event: EventMessage):
        """Route events to the processor."""
        result = await runtime.serverless.invoke_function(
            function_id,
            {"event": event.to_json()}
        )
        if result.is_error:
            print(f"❌ Processing failed: {result.error_message}")
        else:
            print(f"✓ Processed: {result.body}")
    
    await runtime.event_bus.subscribe("*", route_events)
    print("✓ Event routing configured")
    
    # Create and process some test events
    print("\n" + "="*50)
    print("Processing Test Events")
    print("="*50)
    
    test_events = [
        {
            "id": "evt-001",
            "type": "user.login",
            "userID": "local-test-user",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "local-test",
            "data": {
                "ip_address": "127.0.0.1",
                "user_agent": "Local Test Client"
            }
        },
        {
            "id": "evt-002",
            "type": "task.create",
            "userID": "local-test-user",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "local-test",
            "data": {
                "title": "Test Task",
                "description": "This is a test task created locally",
                "priority": "high"
            }
        },
        {
            "id": "evt-003",
            "type": "system.health_check",
            "userID": "system",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "local-test",
            "data": {
                "component": "event_processor",
                "status": "healthy"
            }
        }
    ]
    
    for event_data in test_events:
        print(f"\n📤 Sending: {event_data['type']}")
        event = EventMessage.from_json(json.dumps(event_data))
        await runtime.publish_event(event)
        
        # Give it time to process
        await asyncio.sleep(0.5)
    
    # Wait a bit more for all processing to complete
    await asyncio.sleep(2)
    
    # Show function statistics
    print("\n" + "="*50)
    print("Function Statistics")
    print("="*50)
    
    func_info = await runtime.serverless.get_function(function_id)
    print(f"Function: {func_info['name']}")
    print(f"Invocations: {func_info['invocation_count']}")
    print(f"Last invocation: {func_info['last_invocation']}")
    
    # Show recent logs
    logs = await runtime.serverless.get_function_logs(function_id, max_items=10)
    if logs:
        print("\nRecent Logs:")
        for log in logs[-5:]:  # Show last 5 logs
            print(f"  [{log['timestamp']}] {log['type']}")
    
    # Interactive mode
    print("\n" + "="*50)
    print("Interactive Mode - Send Custom Events")
    print("Type 'quit' to exit")
    print("="*50)
    
    while True:
        print("\nEnter event type (e.g., user.action, task.update):")
        event_type = input("> ").strip()
        
        if event_type.lower() == 'quit':
            break
        
        if not event_type:
            continue
        
        # Create custom event
        custom_event = EventMessage(
            event_type=event_type,
            data={
                "custom": True,
                "created_at": datetime.utcnow().isoformat(),
                "message": f"Custom {event_type} event"
            },
            metadata={"source": "interactive"}
        )
        
        print(f"📤 Sending custom event: {event_type}")
        await runtime.publish_event(custom_event)
        await asyncio.sleep(1)
    
    # Cleanup
    print("\n🛑 Shutting down...")
    await runtime.shutdown()
    print("✓ Shutdown complete")


if __name__ == "__main__":
    import json  # Import here since we use it in the function
    
    print("""
╔════════════════════════════════════════════════════════╗
║          Lightning Core - Local Event Processor        ║
║                                                        ║
║  This runs the universal event processor locally       ║
║  without any cloud dependencies.                       ║
╚════════════════════════════════════════════════════════╝
""")
    
    try:
        asyncio.run(run_local_event_processor())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()