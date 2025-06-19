#!/usr/bin/env python3
"""
Ordered Event-Driven CLI for Vextir OS
Ensures proper conversation ordering in distributed environments
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path

# Load environment variables from .env file
def load_env():
    """Load environment variables from .env file if it exists."""
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

# Load env vars on import
load_env()

from lightning_core.runtime import initialize_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage, FunctionConfig
from lightning_core.abstractions.serverless import RuntimeType
from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)
from lightning_core.vextir_os.conversation_manager import get_conversation_manager


class OrderedVextirCLI:
    """Event-driven CLI with conversation ordering guarantees."""
    
    def __init__(self):
        self.runtime = None
        self.function_id = None
        self.conversation_manager = get_conversation_manager()
        self.pending_responses = {}  # turn_number -> asyncio.Event
        self.response_data = {}      # turn_number -> response_text
        
    async def initialize(self):
        """Initialize runtime and event processor."""
        # Configure environment
        configure_drivers_for_environment()
        await initialize_required_drivers()
        
        # Start conversation manager
        await self.conversation_manager.start()
        
        # Initialize runtime
        config = RuntimeConfig(
            mode=ExecutionMode.LOCAL,
            storage_provider="local",
            storage_path="./data/ordered_cli",
            event_bus_provider="local"
        )
        
        self.runtime = await initialize_runtime(config)
        
        # Ensure event bus is started
        if hasattr(self.runtime.event_bus, '_running') and not self.runtime.event_bus._running:
            await self.runtime.event_bus.start()
        
        # Deploy event processor
        function_config = FunctionConfig(
            name="ordered-cli-processor",
            handler="universal_event_processor_handler",
            runtime=RuntimeType.PYTHON,
            memory_mb=256,
            timeout_seconds=60
        )
        
        self.function_id = await self.runtime.serverless.deploy_function(
            config=function_config,
            handler=universal_event_processor_handler
        )
        
        # Set up event routing
        await self._setup_event_routing()
        
    async def _setup_event_routing(self):
        """Set up routing with conversation ordering."""
        async def route_event(event: EventMessage):
            """Route events to the processor."""
            # Skip routing response events to avoid loops
            if event.event_type.endswith('.response'):
                return
                
            # For chat events, check if turn number already assigned
            if event.event_type == "llm.chat" and "turn_number" not in event.metadata:
                try:
                    # Process through conversation manager if not already processed
                    turn_number, ordered_messages = await self.conversation_manager.process_user_event(event)
                    
                    # Update event data with ordered conversation
                    event.data["messages"] = ordered_messages
                    event.metadata["turn_number"] = turn_number
                    
                    # Track pending response
                    self.pending_responses[turn_number] = asyncio.Event()
                    
                except Exception as e:
                    print(f"[ERROR] Failed to process conversation: {e}")
                    return
            
            result = await self.runtime.serverless.invoke_function(
                self.function_id,
                json.loads(event.to_json())
            )
            
            if result.is_error:
                print(f"[ERROR] Processing failed: {result.error_message}")
            else:
                # Publish output events back to the event bus
                if result.body and isinstance(result.body, dict):
                    output_events = result.body.get('output_events', [])
                    for output_event_data in output_events:
                        output_event = EventMessage(
                            event_type=output_event_data.get('type', 'unknown'),
                            data=output_event_data.get('data', {}),
                            metadata=output_event_data.get('metadata', {})
                        )
                        await self.runtime.event_bus.publish(output_event)
        
        # Subscribe to all events for routing
        await self.runtime.event_bus.subscribe("*", route_event)
        
        # Subscribe to response events
        await self.runtime.event_bus.subscribe("llm.chat.response", self._handle_ordered_response)
        
    async def _handle_ordered_response(self, event: EventMessage):
        """Handle chat responses with ordering."""
        turn_number = event.metadata.get("turn_number")
        if turn_number is None:
            print("[WARNING] Response missing turn number")
            return
        
        # Store response
        response_text = event.data.get("response", "")
        self.response_data[turn_number] = response_text
        
        # Add to conversation manager
        session_id = event.metadata.get("session_id")
        if session_id:
            await self.conversation_manager.process_assistant_event(event, turn_number)
        
        # Signal response received
        if turn_number in self.pending_responses:
            self.pending_responses[turn_number].set()
    
    async def wait_for_turn(self, turn_number: int, timeout: float = 30.0) -> Optional[str]:
        """Wait for a specific turn's response."""
        if turn_number not in self.pending_responses:
            return None
        
        try:
            await asyncio.wait_for(
                self.pending_responses[turn_number].wait(),
                timeout=timeout
            )
            return self.response_data.get(turn_number)
        except asyncio.TimeoutError:
            return None
        finally:
            # Cleanup
            self.pending_responses.pop(turn_number, None)
            self.response_data.pop(turn_number, None)
    
    async def chat_interactive(self, model: str = None, temperature: float = 0.7):
        """Interactive chat session with ordering guarantees."""
        print("🤖 Vextir OS Chat (Ordered Event-Driven)")
        print("Type 'quit' to exit\n")
        
        session_id = f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        session = await self.conversation_manager.get_or_create_session(session_id, "cli_user")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                    
                if not user_input:
                    continue
                
                # Create chat event
                chat_event = EventMessage(
                    event_type="llm.chat",
                    data={
                        "messages": [{"role": "user", "content": user_input}],
                        "model": model or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                        "temperature": temperature
                    },
                    metadata={
                        "source": "ordered_cli",
                        "user_id": "cli_user",
                        "session_id": session_id
                    }
                )
                
                print("⏳ Processing...")
                
                # Process through conversation manager first to get turn number
                turn_number, ordered_messages = await self.conversation_manager.process_user_event(chat_event)
                
                # Update event with ordered messages and turn number
                chat_event.data["messages"] = ordered_messages
                chat_event.metadata["turn_number"] = turn_number
                
                # Track pending response
                self.pending_responses[turn_number] = asyncio.Event()
                
                # Send event
                await self.runtime.publish_event(chat_event)
                
                # Wait for this turn's response
                response_text = await self.wait_for_turn(turn_number)
                
                if response_text:
                    print(f"Assistant: {response_text}\n")
                else:
                    print("Response timeout - please try again\n")
                    
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}\n")
    
    async def show_session_info(self):
        """Display information about active sessions."""
        print("\n📊 Active Conversation Sessions:")
        for session_id, session in self.conversation_manager.sessions.items():
            print(f"\nSession: {session_id}")
            print(f"  User: {session.user_id}")
            print(f"  Created: {session.created_at}")
            print(f"  Turns: {session.current_turn}")
            
            # Show last few turns
            recent_turns = session.turns[-3:] if len(session.turns) > 3 else session.turns
            for turn in recent_turns:
                print(f"\n  Turn {turn.turn_number}:")
                print(f"    User: {turn.user_message['content'][:50]}...")
                if turn.assistant_message:
                    print(f"    Assistant: {turn.assistant_message['content'][:50]}...")
                    print(f"    Processing time: {turn.processing_time:.2f}s")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.conversation_manager:
            await self.conversation_manager.stop()
        if self.runtime:
            await self.runtime.shutdown()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ordered Event-Driven Vextir OS CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This CLI ensures proper conversation ordering in distributed environments.

Examples:
  # Interactive chat with ordering guarantees
  python ordered_cli.py chat
  
  # Show active sessions
  python ordered_cli.py sessions
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Interactive chat with ordering')
    chat_parser.add_argument('--model', help='Model to use')
    chat_parser.add_argument('--temperature', type=float, default=0.7)
    
    # Sessions command
    sessions_parser = subparsers.add_parser('sessions', help='Show active sessions')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Initialize CLI
    cli = OrderedVextirCLI()
    
    try:
        print("Initializing Ordered Vextir OS connection...")
        await cli.initialize()
        print("✓ Connected to Vextir OS with ordering guarantees\n")
        
        # Execute command
        if args.command == 'chat':
            await cli.chat_interactive(args.model, args.temperature)
        elif args.command == 'sessions':
            await cli.show_session_info()
        
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await cli.shutdown()


def main_sync():
    """Synchronous entry point."""
    return asyncio.run(main())


if __name__ == "__main__":
    sys.exit(main_sync())