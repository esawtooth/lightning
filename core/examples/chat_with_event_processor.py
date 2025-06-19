#!/usr/bin/env python3
"""
Complete Chat Example with Event Processor

This shows the full event flow:
1. User sends a chat message
2. Event processor routes it to ChatAgentDriver
3. ChatAgentDriver processes and responds
4. Response is sent back through events
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import (
    RuntimeConfig, ExecutionMode, EventMessage, 
    FunctionConfig
)
from lightning_core.abstractions.serverless import RuntimeType
from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def chat_with_vextir():
    """Run a complete chat example with Vextir OS."""
    
    print("""
╔════════════════════════════════════════════════════════╗
║            Lightning Chat with Vextir OS               ║
║                                                        ║
║  This demonstrates a complete chat system using:       ║
║  - Event-driven architecture                           ║
║  - Local event processor                              ║
║  - ChatAgentDriver for AI responses                   ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # Configure environment
    configure_drivers_for_environment()
    
    # Initialize drivers
    print("🔧 Initializing drivers...")
    await initialize_required_drivers()
    
    # Create runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/chat_vextir",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    print("✓ Runtime initialized")
    
    # Deploy the event processor
    print("\n📦 Deploying event processor...")
    function_config = FunctionConfig(
        name="chat-processor",
        handler="universal_event_processor_handler",
        runtime=RuntimeType.PYTHON,
        memory_mb=256,
        timeout_seconds=60
    )
    
    function_id = await runtime.serverless.deploy_function(
        config=function_config,
        handler=universal_event_processor_handler
    )
    print(f"✓ Event processor deployed: {function_id}")
    
    # Set up event routing
    print("\n🔀 Setting up event routing...")
    
    # Track responses
    responses = {}
    response_events = {}
    
    async def route_and_track(event: EventMessage):
        """Route events to processor and track responses."""
        # Process the event
        result = await runtime.serverless.invoke_function(
            function_id,
            {"event": event.to_json()}
        )
        
        # Track chat responses
        if event.event_type == "llm.chat":
            request_id = event.metadata.get("request_id")
            if request_id:
                if result.is_error:
                    responses[request_id] = {"error": result.error_message}
                else:
                    # Parse the response
                    try:
                        response_data = json.loads(result.body) if isinstance(result.body, str) else result.body
                        responses[request_id] = response_data
                        
                        # Notify waiting coroutine
                        if request_id in response_events:
                            response_events[request_id].set()
                    except:
                        responses[request_id] = {"error": "Failed to parse response"}
                        
        elif event.event_type == "notification.send":
            # Handle notification events (chat responses)
            chat_request_id = event.metadata.get("chat_request_id")
            if chat_request_id and chat_request_id in response_events:
                message = event.data.get("message", "")
                responses[chat_request_id] = {"response": message}
                response_events[chat_request_id].set()
    
    # Subscribe to all events
    await runtime.event_bus.subscribe("*", route_and_track)
    print("✓ Event routing configured")
    
    # Helper function to send chat and wait for response
    async def send_chat_message(message: str, conversation_history: list = None) -> str:
        """Send a chat message and wait for response."""
        request_id = f"chat_{datetime.utcnow().timestamp()}"
        
        # Prepare conversation history
        if conversation_history is None:
            conversation_history = []
        
        # Add current message
        conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # Create response event
        response_events[request_id] = asyncio.Event()
        
        # Create chat event
        chat_event = EventMessage(
            event_type="llm.chat",
            data={
                "messages": conversation_history,
                "model": "gpt-3.5-turbo",  # or gpt-4
                "temperature": 0.7
            },
            metadata={
                "request_id": request_id,
                "source": "chat_demo"
            }
        )
        
        # Send event
        await runtime.publish_event(chat_event)
        
        # Wait for response
        try:
            await asyncio.wait_for(
                response_events[request_id].wait(),
                timeout=30.0
            )
            
            response = responses.get(request_id, {})
            if "error" in response:
                return f"Error: {response['error']}"
            else:
                return response.get("response", "No response received")
                
        except asyncio.TimeoutError:
            return "Response timeout - please try again"
        finally:
            # Cleanup
            response_events.pop(request_id, None)
            responses.pop(request_id, None)
    
    # Demo: Simple conversation
    print("\n" + "="*60)
    print("💬 Starting Chat Demo")
    print("="*60)
    
    conversation = []
    
    # Example 1: Simple greeting
    print("\n👤 You: Hello! How are you today?")
    response = await send_chat_message("Hello! How are you today?", conversation)
    print(f"🤖 Assistant: {response}")
    conversation.append({"role": "assistant", "content": response})
    
    await asyncio.sleep(1)
    
    # Example 2: Follow-up question
    print("\n👤 You: Can you tell me about the Lightning system?")
    response = await send_chat_message("Can you tell me about the Lightning system?", conversation)
    print(f"🤖 Assistant: {response}")
    conversation.append({"role": "assistant", "content": response})
    
    await asyncio.sleep(1)
    
    # Example 3: Technical question
    print("\n👤 You: How does the event-driven architecture work?")
    response = await send_chat_message("How does the event-driven architecture work?", conversation)
    print(f"🤖 Assistant: {response}")
    
    # Show event flow diagram
    print("\n" + "="*60)
    print("📊 Event Flow Visualization")
    print("="*60)
    print("""
    User Input
        ↓
    Chat Event (llm.chat)
        ↓
    Event Bus
        ↓
    Event Processor (Serverless Function)
        ↓
    ChatAgentDriver
        ↓
    LLM API Call
        ↓
    Response Event (notification.send)
        ↓
    User Output
    """)
    
    # Show system stats
    print("\n" + "="*60) 
    print("📈 System Statistics")
    print("="*60)
    
    func_info = await runtime.serverless.get_function(function_id)
    print(f"Function: {func_info['name']}")
    print(f"Invocations: {func_info['invocation_count']}")
    print(f"Runtime: {func_info['runtime']}")
    
    # Interactive mode
    print("\n" + "="*60)
    print("🎯 Interactive Mode")
    print("Type your messages or 'quit' to exit")
    print("="*60 + "\n")
    
    try:
        while True:
            user_input = input("👤 You: ").strip()
            
            if user_input.lower() == 'quit':
                break
                
            if not user_input:
                continue
            
            print("⏳ Thinking...")
            response = await send_chat_message(user_input, conversation)
            print(f"🤖 Assistant: {response}\n")
            
            # Update conversation
            conversation.append({"role": "user", "content": user_input})
            conversation.append({"role": "assistant", "content": response})
            
            # Keep conversation manageable
            if len(conversation) > 20:
                conversation = conversation[-20:]
                
    except EOFError:
        print("\n(End of input detected)")
    
    # Cleanup
    print("\n🛑 Shutting down...")
    await runtime.shutdown()
    print("✓ Chat demo completed!")


if __name__ == "__main__":
    try:
        # Check if we have an API key
        import os
        if not os.environ.get("OPENAI_API_KEY"):
            print("⚠️  Warning: OPENAI_API_KEY not set")
            print("The ChatAgentDriver requires an OpenAI API key to function.")
            print("Set it with: export OPENAI_API_KEY='your-key-here'")
            print()
            
        asyncio.run(chat_with_vextir())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()