#!/usr/bin/env python3
"""
Demo: Vextir OS Direct Usage
Shows how to use Vextir OS directly through the universal processor
"""

import asyncio
import os
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

from lightning_core.vextir_os.driver_initialization import initialize_all_drivers
from lightning_core.vextir_os.universal_processor import get_universal_processor
from lightning_core.events.models import LLMChatEvent

async def main():
    """Demo direct Vextir OS usage"""
    print("=== Vextir OS Direct Usage Demo ===\n")
    
    # Initialize all drivers
    print("1. Initializing drivers...")
    await initialize_all_drivers()
    print("✓ Drivers initialized\n")
    
    # Get the universal processor
    processor = get_universal_processor()
    
    # Create a chat event
    print("2. Creating LLMChatEvent...")
    chat_event = LLMChatEvent(
        source="demo",
        user_id="demo_user",
        data={
            "messages": [
                {"role": "user", "content": "What is Vextir OS and how does it work?"}
            ],
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        }
    )
    print(f"✓ Created event: {chat_event.type}")
    print(f"  User message: {chat_event.data['messages'][0]['content']}\n")
    
    # Process the event
    print("3. Processing event through universal processor...")
    output_events = await processor.process_event(chat_event)
    print(f"✓ Processing complete - got {len(output_events)} output events\n")
    
    # Display results
    print("4. Results:")
    for event in output_events:
        if event.type == "llm.chat.response":
            print(f"  Event type: {event.type}")
            print(f"  Response:\n")
            print(f"{event.data.get('response', 'No response')}\n")
            
            # Show token usage
            usage = event.data.get('usage', {})
            if usage:
                print(f"  Token usage:")
                print(f"    - Prompt tokens: {usage.get('prompt_tokens', 0)}")
                print(f"    - Completion tokens: {usage.get('completion_tokens', 0)}")
                print(f"    - Total tokens: {usage.get('total_tokens', 0)}")

if __name__ == "__main__":
    asyncio.run(main()