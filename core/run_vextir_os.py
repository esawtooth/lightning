#!/usr/bin/env python3
"""
Run Vextir OS with Event Processor and Chat Driver

This starts the OS to handle events, including chat events.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage, FunctionConfig
from lightning_core.abstractions.serverless import RuntimeType
from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)

# Import OpenAI for chat handling
from openai import AsyncOpenAI


async def run_vextir_os():
    """Run Vextir OS with event processing and chat capabilities."""
    
    print("""
╔════════════════════════════════════════════════════════╗
║              Vextir OS Event Processor                 ║
║                                                        ║
║  Listening for events on the event bus...             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # Configure environment
    configure_drivers_for_environment()
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/vextir_os",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Runtime initialized")
    
    # Initialize OpenAI client
    client = AsyncOpenAI()
    print("✓ OpenAI client ready")
    
    # Simple chat handler that publishes responses
    async def handle_chat_event(event: EventMessage):
        """Handle chat events and publish responses."""
        if event.event_type != "llm.chat":
            return
            
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing chat event")
        
        # Extract messages
        messages = event.data.get("messages", [])
        if not messages:
            return
            
        # Get the last user message
        last_message = messages[-1]
        if last_message.get("role") == "user":
            print(f"  User: {last_message['content']}")
            
        try:
            # Call OpenAI
            print("  Calling OpenAI API...")
            response = await client.chat.completions.create(
                model=event.data.get("model", "gpt-3.5-turbo"),
                messages=messages,
                temperature=event.data.get("temperature", 0.7),
                max_tokens=150
            )
            
            # Extract response
            ai_message = response.choices[0].message.content
            print(f"  Assistant: {ai_message}")
            
            # Publish response event
            response_event = EventMessage(
                event_type="llm.chat.response",
                data={
                    "response": ai_message,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                },
                metadata={
                    "request_id": event.metadata.get("request_id"),
                    "original_event_id": event.id,
                    "processor": "vextir_os_chat_handler"
                }
            )
            
            await runtime.publish_event(response_event)
            print("  ✓ Response published")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            
            # Publish error event
            error_event = EventMessage(
                event_type="llm.chat.error",
                data={
                    "error": str(e),
                    "event_id": event.id
                },
                metadata={
                    "request_id": event.metadata.get("request_id")
                }
            )
            await runtime.publish_event(error_event)
    
    # Subscribe to chat events
    await runtime.event_bus.subscribe("llm.chat", handle_chat_event)
    
    # Log all events for monitoring
    async def log_event(event: EventMessage):
        """Log all events for monitoring."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Skip logging chat response details to reduce noise
        if event.event_type == "llm.chat.response":
            print(f"[{timestamp}] {event.event_type} (request_id: {event.metadata.get('request_id', 'none')})")
        else:
            print(f"[{timestamp}] {event.event_type}")
    
    await runtime.event_bus.subscribe("*", log_event)
    
    print("\n📡 Vextir OS is running...")
    print("Listening for events on the event bus")
    print("Press Ctrl+C to stop\n")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down Vextir OS...")
        await runtime.shutdown()
        print("✓ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(run_vextir_os())
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()