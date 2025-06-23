#!/usr/bin/env python3
"""
Test Event-Driven Chat

This script sends a chat event and listens for the response,
demonstrating pure event-driven communication.
"""

import asyncio
import os
import uuid
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
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage


async def test_chat():
    """Send a chat event and wait for response."""
    
    print("🤖 Event-Driven Chat Test")
    print("=" * 50)
    
    # Initialize runtime (connect to same event bus)
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/chat_client",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Connected to event bus")
    
    # Generate request ID for correlation
    request_id = str(uuid.uuid4())
    
    # Set up response listener
    response_received = asyncio.Event()
    response_data = None
    
    async def handle_response(event: EventMessage):
        """Handle chat response events."""
        nonlocal response_data
        if event.metadata.get("request_id") == request_id:
            print(f"\n📥 Received response event!")
            print(f"Response: {event.data.get('response')}")
            response_data = event.data
            response_received.set()
    
    # Subscribe to responses
    await runtime.event_bus.subscribe("llm.chat.response", handle_response)
    print("✓ Listening for responses")
    
    # Create chat event
    chat_event = EventMessage(
        event_type="llm.chat",
        data={
            "messages": [
                {"role": "user", "content": "What is Vextir OS in one sentence?"}
            ],
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        },
        metadata={
            "source": "test_client",
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    print(f"\n📤 Sending chat event:")
    print(f"   Type: {chat_event.event_type}")
    print(f"   Request ID: {request_id}")
    print(f"   Message: What is Vextir OS in one sentence?")
    
    # Send event
    await runtime.publish_event(chat_event)
    print("\n⏳ Waiting for response...")
    
    # Wait for response
    try:
        await asyncio.wait_for(response_received.wait(), timeout=30.0)
        
        if response_data:
            print(f"\n✅ Success!")
            print(f"Model: {response_data.get('model', 'unknown')}")
            if 'usage' in response_data:
                usage = response_data['usage']
                print(f"Tokens: {usage['prompt_tokens']} + {usage['completion_tokens']} = {usage['total_tokens']}")
            
    except asyncio.TimeoutError:
        print("\n❌ Timeout - no response received")
        print("Make sure Vextir OS is running (python run_vextir_os.py)")
    
    # Cleanup
    await runtime.shutdown()
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(test_chat())