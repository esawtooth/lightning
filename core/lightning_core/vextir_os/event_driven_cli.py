#!/usr/bin/env python3
"""
Event-Driven Vextir OS CLI

This CLI communicates with Vextir OS exclusively through the event bus,
following the proper event-driven architecture.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
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
from lightning_core.events.models import LLMChatEvent


class VextirCLI:
    """Event-driven CLI that communicates through the event bus."""
    
    def __init__(self):
        self.runtime = None
        self.function_id = None
        self.response_handlers = {}
        self.response_events = {}
        
    async def initialize(self):
        """Initialize runtime and event processor."""
        # Configure environment
        configure_drivers_for_environment()
        await initialize_required_drivers()
        
        # Initialize runtime
        config = RuntimeConfig(
            mode=ExecutionMode.LOCAL,
            storage_provider="local",
            storage_path="./data/vextir_cli",
            event_bus_provider="local"
        )
        
        self.runtime = await initialize_runtime(config)
        
        # Ensure event bus is started
        if hasattr(self.runtime.event_bus, '_running') and not self.runtime.event_bus._running:
            await self.runtime.event_bus.start()
        
        # Deploy event processor
        function_config = FunctionConfig(
            name="cli-processor",
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
        """Set up routing of events through the processor."""
        async def route_event(event: EventMessage):
            """Route events to the processor."""
            # Skip routing response events to avoid loops
            if event.event_type.endswith('.response'):
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
                        # Convert back to EventMessage and publish
                        output_event = EventMessage(
                            event_type=output_event_data.get('type', 'unknown'),
                            data=output_event_data.get('data', {}),
                            metadata=output_event_data.get('metadata', {})
                        )
                        await self.runtime.event_bus.publish(output_event)
        
        # Subscribe to all events for routing
        await self.runtime.event_bus.subscribe("*", route_event)
        
        # Subscribe to response events
        await self.runtime.event_bus.subscribe("llm.chat.response", self._handle_chat_response)
        await self.runtime.event_bus.subscribe("notification.send", self._handle_notification)
        await self.runtime.event_bus.subscribe("system.response", self._handle_system_response)
        
    async def _handle_chat_response(self, event: EventMessage):
        """Handle chat response events."""
        request_id = event.metadata.get("request_id")
        if request_id and request_id in self.response_handlers:
            self.response_handlers[request_id] = event
            if request_id in self.response_events:
                self.response_events[request_id].set()
                
    async def _handle_notification(self, event: EventMessage):
        """Handle notification events."""
        # Check if this is a response to a CLI request
        request_id = event.metadata.get("request_id") or event.metadata.get("chat_request_id")
        if request_id and request_id in self.response_handlers:
            self.response_handlers[request_id] = event
            if request_id in self.response_events:
                self.response_events[request_id].set()
                
    async def _handle_system_response(self, event: EventMessage):
        """Handle system response events."""
        request_id = event.metadata.get("request_id")
        if request_id and request_id in self.response_handlers:
            self.response_handlers[request_id] = event
            if request_id in self.response_events:
                self.response_events[request_id].set()
    
    async def send_and_wait(self, event: EventMessage, timeout: float = 30.0) -> Optional[EventMessage]:
        """Send an event and wait for response."""
        request_id = event.metadata.get("request_id", str(uuid.uuid4()))
        event.metadata["request_id"] = request_id
        
        # Set up response tracking
        self.response_events[request_id] = asyncio.Event()
        self.response_handlers[request_id] = None
        
        # Send event
        await self.runtime.publish_event(event)
        
        # Wait for response
        try:
            await asyncio.wait_for(
                self.response_events[request_id].wait(),
                timeout=timeout
            )
            return self.response_handlers.get(request_id)
        except asyncio.TimeoutError:
            return None
        finally:
            # Cleanup
            self.response_events.pop(request_id, None)
            self.response_handlers.pop(request_id, None)
    
    async def chat_interactive(self, model: str = None, temperature: float = 0.7):
        """Interactive chat session through events."""
        print("🤖 Vextir OS Chat (Event-Driven)")
        print("Type 'quit' to exit\n")
        
        conversation = []
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                    
                if not user_input:
                    continue
                
                # Add to conversation
                conversation.append({"role": "user", "content": user_input})
                
                # Create chat event
                chat_event = EventMessage(
                    event_type="llm.chat",
                    data={
                        "messages": conversation,
                        "model": model or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                        "temperature": temperature
                    },
                    metadata={
                        "source": "cli",
                        "user_id": "cli_user",
                        "session_id": f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    }
                )
                
                print("⏳ Processing...")
                
                # Send and wait for response
                response = await self.send_and_wait(chat_event)
                
                if response:
                    # Extract response text
                    response_text = None
                    if response.event_type == "llm.chat.response":
                        response_text = response.data.get("response")
                    elif response.event_type == "notification.send":
                        response_text = response.data.get("message")
                    
                    if response_text:
                        print(f"Assistant: {response_text}\n")
                        conversation.append({"role": "assistant", "content": response_text})
                    else:
                        print("No response received\n")
                else:
                    print("Response timeout - please try again\n")
                
                # Keep conversation manageable
                if len(conversation) > 20:
                    conversation = conversation[-20:]
                    
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}\n")
    
    async def send_event(self, event_type: str, data: Any = None):
        """Send a single event."""
        event = EventMessage(
            event_type=event_type,
            data=data or {},
            metadata={
                "source": "cli",
                "user_id": "cli_user",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        print(f"📤 Sending event: {event_type}")
        await self.runtime.publish_event(event)
        print("✓ Event sent")
        
        # For some events, wait for response
        if event_type in ["llm.chat", "system.health_check", "driver.list"]:
            print("⏳ Waiting for response...")
            response = await self.send_and_wait(event, timeout=10.0)
            if response:
                print(f"📥 Response: {response.event_type}")
                if response.data:
                    print(json.dumps(response.data, indent=2))
    
    async def process_event_file(self, filepath: str):
        """Process an event from a JSON file."""
        with open(filepath, 'r') as f:
            event_data = json.load(f)
        
        event = EventMessage.from_json(json.dumps(event_data))
        print(f"📤 Processing event from {filepath}")
        print(f"   Type: {event.event_type}")
        
        await self.runtime.publish_event(event)
        print("✓ Event sent to processor")
        
        # Wait a bit for processing
        await asyncio.sleep(2)
    
    async def monitor_events(self):
        """Monitor all events in the system."""
        print("📡 Monitoring Vextir OS Events")
        print("Press Ctrl+C to stop\n")
        
        async def monitor_handler(event: EventMessage):
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {event.event_type}")
            if event.data:
                # Show first 100 chars of data
                data_str = json.dumps(event.data)
                if len(data_str) > 100:
                    data_str = data_str[:97] + "..."
                print(f"  Data: {data_str}")
        
        await self.runtime.event_bus.subscribe("*", monitor_handler)
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.runtime:
            await self.runtime.shutdown()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Event-Driven Vextir OS CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This CLI communicates with Vextir OS exclusively through events.

Examples:
  # Interactive chat
  vextir chat
  
  # Send an event
  vextir send -t llm.chat -d '{"messages": [{"role": "user", "content": "Hello"}]}'
  
  # Process event from file
  vextir process -f event.json
  
  # Monitor all events
  vextir monitor
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Interactive chat through events')
    chat_parser.add_argument('--model', help='Model to use')
    chat_parser.add_argument('--temperature', type=float, default=0.7)
    
    # Send event command
    send_parser = subparsers.add_parser('send', help='Send an event')
    send_parser.add_argument('-t', '--type', required=True, help='Event type')
    send_parser.add_argument('-d', '--data', help='Event data (JSON)')
    
    # Process event file
    process_parser = subparsers.add_parser('process', help='Process event from file')
    process_parser.add_argument('-f', '--file', required=True, help='Event JSON file')
    
    # Monitor events
    monitor_parser = subparsers.add_parser('monitor', help='Monitor all system events')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Initialize CLI
    cli = VextirCLI()
    
    try:
        print("Initializing Vextir OS connection...")
        await cli.initialize()
        print("✓ Connected to Vextir OS\n")
        
        # Execute command
        if args.command == 'chat':
            await cli.chat_interactive(args.model, args.temperature)
        elif args.command == 'send':
            data = None
            if args.data:
                try:
                    data = json.loads(args.data)
                except:
                    data = {"message": args.data}
            await cli.send_event(args.type, data)
        elif args.command == 'process':
            await cli.process_event_file(args.file)
        elif args.command == 'monitor':
            await cli.monitor_events()
        
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