#!/usr/bin/env python3
"""
Simple Chat Example using Vextir OS

This demonstrates how to:
1. Send chat messages as events
2. Process them through the ChatAgentDriver
3. Receive responses through the event system
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)


async def simple_chat_demo():
    """Run a simple chat demonstration."""
    
    print("🤖 Lightning Chat Demo")
    print("=" * 50)
    
    # Configure for local environment
    configure_drivers_for_environment()
    
    # Initialize drivers
    print("Initializing drivers...")
    await initialize_required_drivers()
    
    # Create local runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/chat_demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Runtime initialized\n")
    
    # Subscribe to chat responses
    response_received = asyncio.Event()
    chat_response = None
    
    async def handle_chat_response(event: EventMessage):
        """Handle chat response events."""
        nonlocal chat_response
        if event.event_type == "llm.chat.response":
            chat_response = event.data.get("response", "")
            print(f"\n🤖 Assistant: {chat_response}")
            response_received.set()
    
    # Subscribe to response events
    await runtime.event_bus.subscribe("llm.chat.response", handle_chat_response)
    
    # Chat conversation loop
    print("Chat started! Type 'quit' to exit.\n")
    
    conversation_history = []
    
    while True:
        # Get user input
        user_message = input("👤 You: ").strip()
        
        if user_message.lower() == 'quit':
            break
            
        if not user_message:
            continue
        
        # Add to conversation history
        conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Create chat event
        chat_event = EventMessage(
            event_type="llm.chat",
            data={
                "messages": conversation_history,
                "model": "gpt-4",  # You can change this
                "temperature": 0.7,
                "max_tokens": 500
            },
            metadata={
                "source": "chat_demo",
                "session_id": "demo_session",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Send the chat event
        print("⏳ Thinking...")
        response_received.clear()
        chat_response = None
        
        await runtime.publish_event(chat_event)
        
        # Wait for response (with timeout)
        try:
            await asyncio.wait_for(response_received.wait(), timeout=30.0)
            
            # Add assistant response to history
            if chat_response:
                conversation_history.append({
                    "role": "assistant", 
                    "content": chat_response
                })
                
        except asyncio.TimeoutError:
            print("⚠️  Response timeout - please try again")
    
    print("\n👋 Chat ended. Goodbye!")
    
    # Show conversation summary
    print("\n" + "="*50)
    print("Conversation Summary")
    print("="*50)
    print(f"Total messages: {len(conversation_history)}")
    print(f"User messages: {len([m for m in conversation_history if m['role'] == 'user'])}")
    print(f"Assistant messages: {len([m for m in conversation_history if m['role'] == 'assistant'])}")
    
    # Cleanup
    await runtime.shutdown()


async def advanced_chat_demo():
    """Advanced demo showing context-aware chat."""
    
    print("🧠 Lightning Context-Aware Chat Demo")
    print("=" * 50)
    
    # Configure and initialize
    configure_drivers_for_environment()
    await initialize_required_drivers()
    
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local", 
        storage_path="./data/context_chat_demo",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Runtime initialized\n")
    
    # First, let's add some context to the system
    print("📚 Adding context documents...")
    
    # Add a sample document to context
    context_event = EventMessage(
        event_type="context.document.create",
        data={
            "title": "Company Policies",
            "content": """
            Our company has the following policies:
            1. Work hours are 9 AM to 5 PM Monday-Friday
            2. Remote work is allowed up to 3 days per week
            3. All employees get 20 days of PTO annually
            4. Health insurance covers dental and vision
            5. 401k matching up to 6% of salary
            """,
            "metadata": {
                "category": "HR",
                "tags": ["policies", "benefits", "work"]
            }
        }
    )
    
    await runtime.publish_event(context_event)
    await asyncio.sleep(1)  # Give it time to process
    
    print("✓ Context added\n")
    
    # Set up response handler
    response_received = asyncio.Event()
    chat_response = None
    
    async def handle_response(event: EventMessage):
        nonlocal chat_response
        if event.event_type == "llm.chat.response":
            chat_response = event.data.get("response", "")
            print(f"\n🤖 Assistant: {chat_response}")
            
            # Show if context was used
            if event.data.get("context_used"):
                print("📎 Used context from: Company Policies")
                
            response_received.set()
    
    await runtime.event_bus.subscribe("llm.chat.response", handle_response)
    
    # Demo questions that should use context
    demo_questions = [
        "What are the company work hours?",
        "How many days of remote work are allowed?",
        "What benefits does the company offer?"
    ]
    
    print("Asking context-aware questions:\n")
    
    for question in demo_questions:
        print(f"👤 You: {question}")
        
        # Create chat event with context enabled
        chat_event = EventMessage(
            event_type="llm.chat",
            data={
                "messages": [{"role": "user", "content": question}],
                "use_context": True,  # Enable context search
                "model": "gpt-4",
                "temperature": 0.3  # Lower temp for factual answers
            },
            metadata={
                "source": "context_demo",
                "context_scope": "company_policies"
            }
        )
        
        response_received.clear()
        await runtime.publish_event(chat_event)
        
        try:
            await asyncio.wait_for(response_received.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            print("⚠️  Response timeout")
        
        print()  # Empty line between Q&As
        await asyncio.sleep(1)
    
    await runtime.shutdown()
    print("\n✓ Demo completed!")


if __name__ == "__main__":
    import sys
    import os
    
    # Ensure we're in the right directory
    if not os.path.exists("lightning_core"):
        os.chdir("/home/sam/lightning/core")
    
    print("""
Choose a demo:
1. Simple Chat - Basic conversation
2. Context-Aware Chat - Chat with document context
3. Both demos
    """)
    
    choice = input("Enter choice (1-3): ").strip()
    
    try:
        if choice == "1":
            asyncio.run(simple_chat_demo())
        elif choice == "2":
            asyncio.run(advanced_chat_demo())
        elif choice == "3":
            asyncio.run(simple_chat_demo())
            print("\n" + "="*60 + "\n")
            asyncio.run(advanced_chat_demo())
        else:
            print("Invalid choice!")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()