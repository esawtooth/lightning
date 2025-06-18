#!/usr/bin/env python3
"""
Lightning OS - Local System Demo

This demonstrates the Lightning OS running locally without Docker networking issues.
It shows how the abstraction layer works with local providers.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the core directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "core"))

from lightning_core.abstractions import (
    RuntimeConfig, ExecutionMode, EventMessage, Document
)
from lightning_core.runtime import LightningRuntime


class DemoDocument(Document):
    """Example document for demonstration."""
    def __init__(self, title="", content="", **kwargs):
        super().__init__(**kwargs)
        self.data["title"] = title
        self.data["content"] = content


async def demo_local_system():
    """Demonstrate Lightning OS running locally."""
    
    print("╔════════════════════════════════════════════════════════╗")
    print("║          Lightning OS - Local System Demo              ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()
    
    # Configure for local execution
    print("1. Configuring for local execution...")
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./demo_data",
        event_bus_provider="local",
        container_runtime="docker",
        serverless_provider="local"
    )
    print(f"   ✓ Mode: {config.mode.value}")
    print(f"   ✓ Storage: {config.storage_provider} (path: {config.storage_path})")
    print(f"   ✓ Event Bus: {config.event_bus_provider}")
    print()
    
    # Initialize runtime
    print("2. Initializing Lightning Runtime...")
    runtime = LightningRuntime(config)
    await runtime.initialize()
    print("   ✓ Runtime initialized")
    print()
    
    # Demo 1: Storage Operations
    print("3. Testing Storage Operations...")
    
    # Create storage container
    await runtime.storage.create_container_if_not_exists("demo_documents")
    doc_store = runtime.get_document_store("demo_documents", DemoDocument)
    
    # Create documents
    doc1 = DemoDocument(
        title="Welcome to Lightning OS",
        content="This is a demonstration of local storage.",
        partition_key="demo"
    )
    created_doc = await doc_store.create(doc1)
    print(f"   ✓ Created document: {created_doc.id}")
    
    # Read document
    read_doc = await doc_store.read(created_doc.id, "demo")
    print(f"   ✓ Read document: {read_doc.data['title']}")
    
    # Query documents
    docs = await doc_store.query({"title": "Welcome to Lightning OS"}, partition_key="demo")
    print(f"   ✓ Query found {len(docs)} document(s)")
    print()
    
    # Demo 2: Event Bus Operations
    print("4. Testing Event Bus...")
    
    # Track received events
    received_events = []
    
    async def event_handler(event: EventMessage):
        received_events.append(event)
        print(f"   → Received event: {event.event_type} - {event.data.get('message', '')}")
    
    # Subscribe to events
    subscription_id = await runtime.event_bus.subscribe(
        "demo.*",  # Subscribe to all demo events
        event_handler
    )
    print(f"   ✓ Subscribed to demo.* events (ID: {subscription_id[:8]}...)")
    
    # Publish events
    events_to_send = [
        EventMessage(
            event_type="demo.started",
            data={"message": "Lightning OS demo started", "timestamp": datetime.utcnow().isoformat()}
        ),
        EventMessage(
            event_type="demo.test",
            data={"message": "Testing event bus", "test_id": 123}
        ),
        EventMessage(
            event_type="demo.completed",
            data={"message": "Demo completed successfully"}
        )
    ]
    
    for event in events_to_send:
        await runtime.publish_event(event)
    
    # Wait for events to be processed
    await asyncio.sleep(0.5)
    print(f"   ✓ Published {len(events_to_send)} events")
    print(f"   ✓ Received {len(received_events)} events")
    print()
    
    # Demo 3: Serverless Functions
    print("5. Testing Serverless Functions...")
    
    # Define a simple function
    async def demo_function(context):
        """Demo serverless function."""
        from lightning_core.abstractions.serverless import FunctionResponse
        
        data = context.trigger_data
        result = {
            "processed": True,
            "input": data,
            "timestamp": datetime.utcnow().isoformat(),
            "function": context.function_name
        }
        
        return FunctionResponse(
            status_code=200,
            body=result
        )
    
    # Deploy function
    from lightning_core.abstractions.serverless import FunctionConfig, RuntimeType
    
    func_config = FunctionConfig(
        name="demo-function",
        handler="demo_function",
        runtime=RuntimeType.PYTHON,
        memory_mb=128,
        timeout_seconds=30
    )
    
    function_id = await runtime.serverless.deploy_function(func_config, demo_function)
    print(f"   ✓ Deployed function: {function_id}")
    
    # Invoke function
    response = await runtime.serverless.invoke_function(
        function_id,
        {"message": "Hello from Lightning OS!", "demo": True}
    )
    print(f"   ✓ Function response: {response.status_code}")
    print(f"   ✓ Result: {response.body}")
    print()
    
    # Demo 4: System Status
    print("6. System Status:")
    print(f"   • Mode: {runtime.config.mode.value}")
    print(f"   • Storage: {runtime.config.storage_provider}")
    print(f"   • Event Bus: {runtime.config.event_bus_provider}")
    print(f"   • Serverless: {runtime.config.serverless_provider}")
    print(f"   • Local Mode: {runtime.is_local_mode()}")
    print(f"   • Cloud Mode: {runtime.is_cloud_mode()}")
    print()
    
    # Show what would happen in Azure mode
    print("7. Comparison with Azure Mode:")
    azure_config = RuntimeConfig(
        mode=ExecutionMode.AZURE,
        storage_provider="azure_cosmos",
        event_bus_provider="azure_service_bus",
        container_runtime="azure_aci",
        serverless_provider="azure_functions"
    )
    print("   In Azure mode, the same code would use:")
    print(f"   • Storage: {azure_config.storage_provider} (Cosmos DB)")
    print(f"   • Event Bus: {azure_config.event_bus_provider} (Service Bus)")
    print(f"   • Containers: {azure_config.container_runtime} (Container Instances)")
    print(f"   • Serverless: {azure_config.serverless_provider} (Functions)")
    print()
    
    # Cleanup
    print("8. Cleaning up...")
    await runtime.event_bus.unsubscribe(subscription_id)
    await runtime.serverless.delete_function(function_id)
    await doc_store.delete(created_doc.id, "demo")
    await runtime.shutdown()
    print("   ✓ Cleanup complete")
    print()
    
    print("✨ Demo completed successfully!")
    print()
    print("Key Takeaways:")
    print("• Same code works in both local and cloud environments")
    print("• Switch between providers with configuration only")
    print("• No cloud dependencies needed for development")
    print("• Full functionality available locally")


if __name__ == "__main__":
    # Create demo data directory
    Path("./demo_data").mkdir(exist_ok=True)
    
    # Run the demo
    try:
        asyncio.run(demo_local_system())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()