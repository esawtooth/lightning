#!/usr/bin/env python3
"""
Enhanced Vextir OS CLI with chat integration

Provides a comprehensive command-line interface for:
- Event processing
- Chat interactions
- System monitoring
- Driver management
"""

import argparse
import asyncio
import json
import os
import sys
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
from lightning_core.abstractions import RuntimeConfig, ExecutionMode, EventMessage
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_required_drivers
)


async def chat_command(args):
    """Interactive chat command."""
    # Set API key if provided
    if args.api_key:
        os.environ['OPENAI_API_KEY'] = args.api_key
    
    # Check for API key
    if not os.environ.get('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not set. Use --api-key or set environment variable.")
        return 1
    
    print("🤖 Vextir OS Chat Interface")
    print("Type 'quit' to exit\n")
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/vextir_chat",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Simple OpenAI integration
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    
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
            event = EventMessage(
                event_type="llm.chat",
                data={
                    "messages": conversation,
                    "model": args.model,
                    "temperature": args.temperature
                }
            )
            
            # Process with OpenAI
            print("Thinking...")
            response = await client.chat.completions.create(
                model=args.model,
                messages=conversation,
                temperature=args.temperature
            )
            
            ai_response = response.choices[0].message.content
            print(f"Assistant: {ai_response}\n")
            
            # Add to conversation
            conversation.append({"role": "assistant", "content": ai_response})
            
            # Keep conversation manageable
            if len(conversation) > 20:
                conversation = conversation[-20:]
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    await runtime.shutdown()
    return 0


async def process_event_command(args):
    """Process a single event."""
    # Read event from file or stdin
    if args.file:
        with open(args.file, 'r') as f:
            event_data = json.load(f)
    else:
        event_data = json.load(sys.stdin)
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/vextir_cli",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Create event
    event = EventMessage.from_json(json.dumps(event_data))
    
    # Process event
    print(f"Processing event: {event.event_type}")
    await runtime.publish_event(event)
    
    # Wait a bit for processing
    await asyncio.sleep(2)
    
    print("Event processed")
    await runtime.shutdown()
    return 0


async def list_drivers_command(args):
    """List available drivers."""
    from lightning_core.vextir_os.registries import get_driver_registry
    
    registry = get_driver_registry()
    drivers = registry.list_drivers()
    
    if args.format == 'json':
        driver_data = [
            {
                "id": driver.id,
                "type": driver.type.value,
                "name": driver.name,
                "capabilities": list(driver.capabilities)
            }
            for driver in drivers
        ]
        print(json.dumps(driver_data, indent=2))
    else:
        print("\nAvailable Vextir OS Drivers:")
        print("-" * 50)
        
        for driver in drivers:
            print(f"\n{driver.id} ({driver.type.value})")
            print(f"  Name: {driver.name}")
            print(f"  Capabilities: {', '.join(driver.capabilities)}")


async def run_processor_command(args):
    """Run the event processor."""
    from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
    from lightning_core.abstractions import FunctionConfig
    from lightning_core.abstractions.serverless import RuntimeType
    
    print("Starting Vextir OS Event Processor...")
    
    # Configure environment
    configure_drivers_for_environment()
    await initialize_required_drivers()
    
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/vextir_processor",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Deploy processor
    function_config = FunctionConfig(
        name="vextir-processor",
        handler="universal_event_processor_handler",
        runtime=RuntimeType.PYTHON,
        memory_mb=256,
        timeout_seconds=60
    )
    
    function_id = await runtime.serverless.deploy_function(
        config=function_config,
        handler=universal_event_processor_handler
    )
    
    print(f"✓ Processor deployed: {function_id}")
    print("✓ Listening for events...")
    print("\nPress Ctrl+C to stop\n")
    
    # Route events to processor
    async def route_events(event: EventMessage):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing: {event.event_type}")
        result = await runtime.serverless.invoke_function(
            function_id,
            {"event": event.to_json()}
        )
        if result.is_error:
            print(f"  ❌ Error: {result.error_message}")
        else:
            print(f"  ✓ Processed")
    
    await runtime.event_bus.subscribe("*", route_events)
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await runtime.shutdown()
    
    return 0


async def send_event_command(args):
    """Send a quick event."""
    # Initialize runtime
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/vextir_send",
        event_bus_provider="local"
    )
    
    runtime = await initialize_runtime(config)
    
    # Parse data if provided
    data = {}
    if args.data:
        try:
            data = json.loads(args.data)
        except:
            # Treat as string message
            data = {"message": args.data}
    
    # Create event
    event = EventMessage(
        event_type=args.type,
        data=data,
        metadata={
            "source": "cli",
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    print(f"Sending event: {args.type}")
    await runtime.publish_event(event)
    print("✓ Event sent")
    
    await runtime.shutdown()
    return 0


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Vextir OS Command Line Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive chat
  vextir chat
  
  # Process an event from file
  vextir process-event -f event.json
  
  # Run the event processor
  vextir run-processor
  
  # Send a quick event
  vextir send-event -t user.message -d '{"text": "Hello"}'
  
  # List available drivers
  vextir list-drivers
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Interactive chat interface')
    chat_parser.add_argument('--model', default='gpt-3.5-turbo', help='Model to use')
    chat_parser.add_argument('--temperature', type=float, default=0.7, help='Temperature')
    chat_parser.add_argument('--api-key', help='OpenAI API key')
    
    # Process event command
    process_parser = subparsers.add_parser('process-event', help='Process a single event')
    process_parser.add_argument('-f', '--file', help='Event JSON file (default: stdin)')
    
    # List drivers command
    list_parser = subparsers.add_parser('list-drivers', help='List available drivers')
    list_parser.add_argument('--format', choices=['table', 'json'], default='table')
    
    # Run processor command
    run_parser = subparsers.add_parser('run-processor', help='Run the event processor')
    
    # Send event command
    send_parser = subparsers.add_parser('send-event', help='Send a quick event')
    send_parser.add_argument('-t', '--type', required=True, help='Event type')
    send_parser.add_argument('-d', '--data', help='Event data (JSON or string)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to appropriate command
    if args.command == 'chat':
        return await chat_command(args)
    elif args.command == 'process-event':
        return await process_event_command(args)
    elif args.command == 'list-drivers':
        return await list_drivers_command(args)
    elif args.command == 'run-processor':
        return await run_processor_command(args)
    elif args.command == 'send-event':
        return await send_event_command(args)
    
    return 0


def main_sync():
    """Synchronous entry point."""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main_sync())