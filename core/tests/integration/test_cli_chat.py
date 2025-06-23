#!/usr/bin/env python3
"""
Test CLI Chat - Demonstrates event-driven chat through the CLI
"""

import asyncio
import os
from pathlib import Path

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
from openai import AsyncOpenAI


async def run_os_processor():
    """Run a simple OS processor that handles chat events."""
    print("[OS] Starting Vextir OS processor...")
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/os_processor",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Ensure event bus is started
    if hasattr(runtime.event_bus, '_running') and not runtime.event_bus._running:
        await runtime.event_bus.start()
    
    client = AsyncOpenAI()
    
    # Chat handler
    async def handle_chat(event: EventMessage):
        if event.event_type != "llm.chat":
            return
            
        print(f"[OS] Processing chat event from {event.metadata.get('source', 'unknown')}")
        messages = event.data.get("messages", [])
        
        if messages:
            user_msg = messages[-1]["content"]
            print(f"[OS] User asked: '{user_msg}'")
            
            # Call OpenAI
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=50
            )
            
            ai_response = response.choices[0].message.content
            print(f"[OS] AI response: '{ai_response}'")
            
            # Publish response
            response_event = EventMessage(
                event_type="llm.chat.response",
                data={"response": ai_response},
                metadata={
                    "request_id": event.metadata.get("request_id"),
                    "processor": "os_processor"
                }
            )
            
            await runtime.publish_event(response_event)
            print("[OS] Response published")
    
    # Subscribe to chat events
    await runtime.event_bus.subscribe("llm.chat", handle_chat)
    print("[OS] Ready to process chat events")
    
    # Keep running for 30 seconds
    await asyncio.sleep(30)
    await runtime.shutdown()


async def run_cli_client():
    """Run CLI client that sends chat messages."""
    # Wait for OS to start
    await asyncio.sleep(2)
    
    print("\n[CLI] Starting CLI client...")
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/cli_client",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Ensure event bus is started
    if hasattr(runtime.event_bus, '_running') and not runtime.event_bus._running:
        await runtime.event_bus.start()
    
    # Test messages
    test_messages = [
        "What is event-driven architecture?",
        "What is Vextir OS?",
        "How does the event bus work?"
    ]
    
    for i, message in enumerate(test_messages):
        print(f"\n[CLI] Sending message {i+1}: '{message}'")
        
        request_id = f"cli_test_{i}"
        response_received = asyncio.Event()
        response_text = None
        
        # Response handler
        async def handle_response(event: EventMessage):
            nonlocal response_text
            if event.metadata.get("request_id") == request_id:
                response_text = event.data.get("response")
                print(f"[CLI] Received response: '{response_text}'")
                response_received.set()
        
        # Subscribe to responses
        sub_id = await runtime.event_bus.subscribe("llm.chat.response", handle_response)
        
        # Send chat event
        chat_event = EventMessage(
            event_type="llm.chat",
            data={
                "messages": [{"role": "user", "content": message}]
            },
            metadata={
                "source": "cli",
                "request_id": request_id
            }
        )
        
        await runtime.publish_event(chat_event)
        
        # Wait for response
        try:
            await asyncio.wait_for(response_received.wait(), timeout=10.0)
            print(f"[CLI] ✓ Got response successfully")
        except asyncio.TimeoutError:
            print(f"[CLI] ✗ Timeout waiting for response")
        
        # Unsubscribe to avoid handler buildup
        await runtime.event_bus.unsubscribe(sub_id)
        
        # Brief pause between messages
        await asyncio.sleep(1)
    
    print("\n[CLI] Test complete")
    await runtime.shutdown()


async def main():
    """Run both OS processor and CLI client."""
    print("""
EVENT-DRIVEN CHAT TEST
======================

This demonstrates the CLI communicating with Vextir OS
purely through events - no direct service calls.
""")
    
    # Run both concurrently
    os_task = asyncio.create_task(run_os_processor())
    cli_task = asyncio.create_task(run_cli_client())
    
    # Wait for CLI to finish
    await cli_task
    
    # Cancel OS task
    os_task.cancel()
    try:
        await os_task
    except asyncio.CancelledError:
        pass
    
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())