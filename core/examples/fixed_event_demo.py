#!/usr/bin/env python3
"""
Fixed Event-Driven Demo - Ensures event bus is properly started
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / '.env'
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


async def fixed_demo():
    """Fixed event-driven demo that ensures event bus is running."""
    
    print("""
FIXED EVENT-DRIVEN CHAT DEMO
============================
""")
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/fixed_demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    client = AsyncOpenAI()
    
    # IMPORTANT: Ensure event bus is started
    if hasattr(runtime.event_bus, '_running'):
        print(f"Event bus running: {runtime.event_bus._running}")
        if not runtime.event_bus._running:
            print("Starting event bus manually...")
            await runtime.event_bus.start()
    
    print("✓ System ready\n")
    
    # Set up handlers FIRST (before publishing)
    response_received = asyncio.Event()
    response_text = None
    
    # Response handler
    async def handle_response(event: EventMessage):
        nonlocal response_text
        print(f"[CLI] Received response: {event.data.get('response')}")
        response_text = event.data.get('response')
        response_received.set()
    
    # Chat processor
    async def process_chat(event: EventMessage):
        print(f"\n[OS] Processing: {event.event_type}")
        messages = event.data.get("messages", [])
        
        if messages:
            print(f"[OS] User: {messages[-1]['content']}")
            
            # Call OpenAI
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=50
            )
            
            ai_text = response.choices[0].message.content
            print(f"[OS] AI: {ai_text}")
            
            # Publish response
            await runtime.publish_event(EventMessage(
                event_type="llm.chat.response",
                data={"response": ai_text},
                metadata={"request_id": event.metadata.get("request_id")}
            ))
    
    # Subscribe BEFORE publishing
    await runtime.event_bus.subscribe("llm.chat.response", handle_response)
    await runtime.event_bus.subscribe("llm.chat", process_chat)
    
    print("DEMONSTRATION:")
    print("-" * 50)
    
    # Send chat event
    print("\n[CLI] Sending: What is Vextir OS?")
    
    await runtime.publish_event(EventMessage(
        event_type="llm.chat",
        data={
            "messages": [{"role": "user", "content": "What is Vextir OS in 10 words?"}]
        },
        metadata={"request_id": "demo_123"}
    ))
    
    # Wait with timeout
    try:
        await asyncio.wait_for(response_received.wait(), timeout=10.0)
        print(f"\n✅ Success! Got response: '{response_text}'")
    except asyncio.TimeoutError:
        print("\n❌ Timeout - checking event bus status...")
        if hasattr(runtime.event_bus, '_running'):
            print(f"   Event bus running: {runtime.event_bus._running}")
        if hasattr(runtime.event_bus, '_tasks'):
            print(f"   Active tasks: {len(runtime.event_bus._tasks)}")
            for task in runtime.event_bus._tasks:
                print(f"     {task}")
    
    await runtime.shutdown()


if __name__ == "__main__":
    asyncio.run(fixed_demo())