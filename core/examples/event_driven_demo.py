#!/usr/bin/env python3
"""
Event-Driven Chat Demo - Shows CLI → Event Bus → Processor → Response
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


async def event_driven_demo():
    """Complete event-driven chat demonstration."""
    
    print("""
    EVENT-DRIVEN CHAT ARCHITECTURE DEMO
    ==================================
    
    This demo shows how the CLI communicates ONLY through events.
    """)
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    client = AsyncOpenAI()
    
    print("✓ Event bus initialized")
    print("\nSETUP:")
    print("------")
    
    # 1. Set up the "OS" side - event processor
    async def chat_processor(event: EventMessage):
        """This runs in Vextir OS - processes chat events."""
        if event.event_type != "llm.chat":
            return
            
        print(f"\n  [OS] Received event: {event.event_type}")
        print(f"  [OS] Request ID: {event.metadata.get('request_id')}")
        
        messages = event.data.get("messages", [])
        if messages:
            print(f"  [OS] Processing: '{messages[-1]['content']}'")
            
            # Call OpenAI
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=50
            )
            
            ai_text = response.choices[0].message.content
            print(f"  [OS] Response: '{ai_text}'")
            
            # Publish response event
            response_event = EventMessage(
                event_type="llm.chat.response",
                data={"response": ai_text},
                metadata={"request_id": event.metadata.get("request_id")}
            )
            
            await runtime.publish_event(response_event)
            print(f"  [OS] Published response event")
    
    # Subscribe processor
    await runtime.event_bus.subscribe("llm.chat", chat_processor)
    print("1. Chat processor subscribed to 'llm.chat' events")
    
    # 2. CLI side - send event and wait for response
    print("\n2. CLI preparing to send event...")
    
    request_id = "demo_123"
    response_received = asyncio.Event()
    cli_response = None
    
    async def response_handler(event: EventMessage):
        """CLI's response handler."""
        nonlocal cli_response
        if event.metadata.get("request_id") == request_id:
            print(f"\n  [CLI] Received response event!")
            cli_response = event.data.get("response")
            response_received.set()
    
    await runtime.event_bus.subscribe("llm.chat.response", response_handler)
    print("3. CLI subscribed to 'llm.chat.response' events")
    
    # Send the event
    print("\nEXECUTION:")
    print("----------")
    print("\n[CLI] Creating chat event...")
    
    chat_event = EventMessage(
        event_type="llm.chat",
        data={
            "messages": [
                {"role": "user", "content": "What is event-driven architecture in 10 words?"}
            ]
        },
        metadata={"request_id": request_id, "source": "cli"}
    )
    
    print(f"[CLI] Publishing event to bus...")
    await runtime.publish_event(chat_event)
    
    # Wait for response
    print("[CLI] Waiting for response...")
    await asyncio.wait_for(response_received.wait(), timeout=10.0)
    
    print(f"\n[CLI] Got response: '{cli_response}'")
    
    # Summary
    print("\n\nSUMMARY:")
    print("--------")
    print("""
    1. CLI created an event (NOT a direct OpenAI call)
    2. Event published to event bus
    3. OS processor received the event
    4. OS processor called OpenAI
    5. OS processor published response event
    6. CLI received response from event bus
    
    The CLI never knew about OpenAI - pure event-driven!
    """)
    
    await runtime.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(event_driven_demo())
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()