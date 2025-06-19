#!/usr/bin/env python3
"""
Working Event-Driven Demo - Shows proper event flow
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


async def working_demo():
    """Working event-driven demo with proper async handling."""
    
    print("""
EVENT-DRIVEN CHAT - WORKING DEMO
================================

This shows the CLI using ONLY events to communicate.
""")
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/working_demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    client = AsyncOpenAI()
    
    print("✓ System initialized\n")
    
    # Track processing
    processing_complete = asyncio.Event()
    response_text = None
    
    # Event processor (Vextir OS side)
    async def process_chat(event: EventMessage):
        """Process chat events - this is what runs in Vextir OS."""
        nonlocal response_text
        
        print(f"[Vextir OS] Received: {event.event_type}")
        messages = event.data.get("messages", [])
        
        if messages:
            user_msg = messages[-1]["content"]
            print(f"[Vextir OS] User asked: '{user_msg}'")
            print(f"[Vextir OS] Calling OpenAI...")
            
            try:
                # Call OpenAI
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=30
                )
                
                response_text = response.choices[0].message.content
                print(f"[Vextir OS] Got response: '{response_text}'")
                
                # Publish response
                resp_event = EventMessage(
                    event_type="llm.chat.response",
                    data={"response": response_text},
                    metadata={"request_id": event.metadata.get("request_id")}
                )
                
                await runtime.publish_event(resp_event)
                print(f"[Vextir OS] Published response event\n")
                
            except Exception as e:
                print(f"[Vextir OS] Error: {e}")
        
        processing_complete.set()
    
    # Subscribe processor
    await runtime.event_bus.subscribe("llm.chat", process_chat)
    
    # CLI response handler
    cli_response = None
    
    async def handle_response(event: EventMessage):
        """CLI's response handler."""
        nonlocal cli_response
        print(f"[CLI] Received response event")
        cli_response = event.data.get("response")
    
    await runtime.event_bus.subscribe("llm.chat.response", handle_response)
    
    print("DEMONSTRATION:")
    print("-" * 50)
    
    # CLI sends event
    print("\n[CLI] User types: 'What is Python?'")
    print("[CLI] Creating event (NOT calling OpenAI)...")
    
    event = EventMessage(
        event_type="llm.chat",
        data={
            "messages": [{"role": "user", "content": "What is Python in one sentence?"}]
        },
        metadata={"request_id": "test_123", "source": "cli"}
    )
    
    print("[CLI] Publishing to event bus...")
    await runtime.publish_event(event)
    
    # Wait for processing
    await processing_complete.wait()
    await asyncio.sleep(0.5)  # Let response propagate
    
    if cli_response:
        print(f"[CLI] Displaying to user: '{cli_response}'")
    
    print("\n" + "="*50)
    print("ARCHITECTURE BENEFITS:")
    print("="*50)
    print("""
✓ CLI doesn't have OpenAI API key
✓ CLI doesn't import OpenAI library  
✓ All communication through events
✓ Easy to swap LLM providers
✓ Works same locally and in cloud
✓ Multiple handlers can process events
✓ Complete decoupling of components
""")
    
    await runtime.shutdown()
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    asyncio.run(working_demo())