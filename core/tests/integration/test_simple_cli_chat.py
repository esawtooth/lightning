#!/usr/bin/env python3
"""
Simple CLI Chat Test - Direct event-driven chat without complex drivers
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
from lightning_core.vextir_os.event_driven_cli import VextirCLI


async def test_cli_chat():
    """Test the event-driven CLI chat functionality."""
    
    print("""
TESTING EVENT-DRIVEN CLI CHAT
=============================

This tests the CLI's event-driven chat without complex driver initialization.
""")
    
    # Initialize CLI
    cli = VextirCLI()
    
    # Initialize with minimal setup
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/test_cli",
        event_bus_provider="local"
    )
    
    cli.runtime = await initialize_runtime(config)
    
    # Ensure event bus is started
    if hasattr(cli.runtime.event_bus, '_running') and not cli.runtime.event_bus._running:
        await cli.runtime.event_bus.start()
    
    # Set up simple chat processor
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    
    async def simple_chat_processor(event: EventMessage):
        """Simple chat processor for testing."""
        if event.event_type != "llm.chat":
            return
            
        print(f"[Processor] Handling chat event")
        messages = event.data.get("messages", [])
        
        if messages:
            # Call OpenAI
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=50
            )
            
            # Publish response
            response_event = EventMessage(
                event_type="llm.chat.response",
                data={"response": response.choices[0].message.content},
                metadata={"request_id": event.metadata.get("request_id")}
            )
            
            await cli.runtime.publish_event(response_event)
    
    # Subscribe processor
    await cli.runtime.event_bus.subscribe("llm.chat", simple_chat_processor)
    
    # Set up CLI response handlers
    await cli._setup_event_routing()
    
    # Test sending a message
    print("\nTesting chat through CLI...")
    
    # Send test message
    test_event = EventMessage(
        event_type="llm.chat",
        data={
            "messages": [{"role": "user", "content": "What is Vextir OS in one sentence?"}]
        },
        metadata={"source": "cli_test", "request_id": "test_123"}
    )
    
    print(f"[CLI] Sending: {test_event.data['messages'][0]['content']}")
    
    response = await cli.send_and_wait(test_event, timeout=10.0)
    
    if response:
        print(f"[CLI] Response: {response.data.get('response')}")
        print("\n✅ CLI chat working correctly!")
    else:
        print("\n❌ No response received")
    
    await cli.runtime.shutdown()


if __name__ == "__main__":
    asyncio.run(test_cli_chat())