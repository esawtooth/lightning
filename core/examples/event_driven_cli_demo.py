#!/usr/bin/env python3
"""
Demo: Event-Driven CLI Architecture

Shows how the CLI communicates ONLY through events, never directly with services.
"""

import asyncio
import json
from datetime import datetime

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage


async def demo_event_driven_cli():
    """Demonstrate event-driven CLI communication."""
    
    print("""
╔════════════════════════════════════════════════════════╗
║        Event-Driven CLI Architecture Demo              ║
║                                                        ║
║  CLI → Event Bus → Processor → Service → Event Bus    ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/cli_demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Event bus initialized\n")
    
    # Simulate a simple event processor
    async def mock_chat_processor(event: EventMessage):
        """Mock processor that handles chat events."""
        if event.event_type == "llm.chat":
            print(f"  [Processor] Received chat event from {event.metadata.get('source', 'unknown')}")
            messages = event.data.get("messages", [])
            
            if messages:
                last_msg = messages[-1]["content"]
                print(f"  [Processor] User said: '{last_msg}'")
                print(f"  [Processor] Would call OpenAI here...")
                
                # Simulate response
                response_event = EventMessage(
                    event_type="llm.chat.response",
                    data={
                        "response": f"Mock response to: {last_msg}",
                        "model": "mock-model"
                    },
                    metadata={
                        "request_id": event.metadata.get("request_id"),
                        "processor": "mock_chat_processor"
                    }
                )
                
                print(f"  [Processor] Publishing response event")
                await runtime.publish_event(response_event)
    
    # Subscribe processor to events
    await runtime.event_bus.subscribe("llm.chat", mock_chat_processor)
    
    print("📊 Event Flow Demonstration")
    print("="*50)
    
    # Simulate CLI sending a chat event
    print("\n1. CLI sends chat event:")
    print("   CLI: Creating event with user message")
    
    cli_event = EventMessage(
        event_type="llm.chat",
        data={
            "messages": [
                {"role": "user", "content": "What is event-driven architecture?"}
            ],
            "model": "gpt-3.5-turbo"
        },
        metadata={
            "source": "cli",
            "request_id": "cli_123",
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    print(f"   CLI: Publishing event to bus (type: {cli_event.event_type})")
    
    # Set up response listener (CLI would do this)
    response_received = asyncio.Event()
    cli_response = None
    
    async def cli_response_handler(event: EventMessage):
        nonlocal cli_response
        if event.metadata.get("request_id") == "cli_123":
            print(f"\n3. CLI receives response:")
            print(f"   CLI: Got response event (type: {event.event_type})")
            print(f"   CLI: Response text: '{event.data.get('response')}'")
            cli_response = event
            response_received.set()
    
    await runtime.event_bus.subscribe("llm.chat.response", cli_response_handler)
    
    # Send the event
    await runtime.publish_event(cli_event)
    
    print("\n2. Processor handles event:")
    await asyncio.sleep(0.5)  # Give processor time
    
    # Wait for response
    await response_received.wait()
    
    print("\n" + "="*50)
    print("✅ Complete Event Flow:")
    print("""
    1. CLI creates EventMessage (never calls OpenAI directly)
    2. CLI publishes to Event Bus
    3. Processor receives event from bus
    4. Processor calls external service (OpenAI)
    5. Processor publishes response event
    6. CLI receives response from bus
    7. CLI displays to user
    
    Benefits:
    - CLI is decoupled from services
    - Easy to swap implementations
    - All communication is traceable
    - Works locally and in cloud
    - Multiple handlers can process events
    """)
    
    # Show what NOT to do
    print("\n❌ What NOT to do in CLI:")
    print("""
    # BAD - Direct service calls:
    client = OpenAI()
    response = client.chat.completions.create(...)
    
    # GOOD - Event-driven:
    event = EventMessage(type="llm.chat", data={...})
    await runtime.publish_event(event)
    # Wait for response event
    """)
    
    await runtime.shutdown()
    print("\n✓ Demo completed")


if __name__ == "__main__":
    asyncio.run(demo_event_driven_cli())