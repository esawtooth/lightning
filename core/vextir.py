#!/usr/bin/env python3
"""
Vextir OS - Unified Command Line Interface
Event-driven AI operating system
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
def load_env():
    """Load environment variables from .env file if it exists."""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

# Load env vars on import
load_env()

from lightning_core.vextir_os.event_driven_cli import VextirCLI

# ANSI color codes for beautiful output
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'
    GRAY = '\033[90m'

def print_status(message, status="info"):
    """Print a status message with color"""
    if status == "success":
        print(f"{Colors.GREEN}✓{Colors.END} {message}")
    elif status == "error":
        print(f"{Colors.RED}✗{Colors.END} {message}")
    elif status == "info":
        print(f"{Colors.BLUE}ℹ{Colors.END} {message}")
    else:
        print(f"• {message}")

def print_header():
    """Print Vextir OS header"""
    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔══════════════════════════════════════╗")
    print("║           VEXTIR OS CLI              ║")
    print("║      Event-Driven AI System          ║")
    print("╚══════════════════════════════════════╝")
    print(f"{Colors.END}")

async def cmd_chat(args):
    """Interactive chat command"""
    print_header()
    print_status("Starting interactive chat session")
    print_status("Initializing Vextir OS connection...")
    
    cli = VextirCLI()
    try:
        await cli.initialize()
        print_status("Connected to Vextir OS", "success")
        print()
        print(f"{Colors.BOLD}Vextir OS Chat{Colors.END}")
        print("Type 'quit' to exit\n")
        
        conversation = []
        
        while True:
            try:
                user_input = input(f"{Colors.GREEN}You:{Colors.END} ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    break
                    
                if not user_input:
                    continue
                
                conversation.append({"role": "user", "content": user_input})
                
                # Create chat event
                from lightning_core.abstractions import EventMessage
                chat_event = EventMessage(
                    event_type="llm.chat",
                    data={
                        "messages": conversation,
                        "model": args.model or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                        "temperature": args.temperature
                    },
                    metadata={
                        "source": "vextir_cli",
                        "user_id": "interactive_user",
                        "session_id": f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    }
                )
                
                print(f"{Colors.YELLOW}⏳ Processing...{Colors.END}")
                
                response = await cli.send_and_wait(chat_event, timeout=30.0)
                
                if response:
                    response_text = response.data.get("response", "")
                    if response_text:
                        print(f"\n{Colors.BLUE}Assistant:{Colors.END} {response_text}\n")
                        conversation.append({"role": "assistant", "content": response_text})
                        
                        # Show token usage
                        usage = response.data.get("usage", {})
                        if usage and args.verbose:
                            tokens = usage.get("total_tokens", 0)
                            print(f"{Colors.GRAY}[Tokens: {tokens}]{Colors.END}")
                    else:
                        print_status("Empty response received", "error")
                else:
                    print_status("Response timeout - please try again", "error")
                
                # Keep conversation manageable
                if len(conversation) > 20:
                    conversation = conversation[-20:]
                    if args.verbose:
                        print_status("Conversation trimmed to last 20 messages", "info")
                        
            except KeyboardInterrupt:
                print("\n")
                break
            except Exception as e:
                print_status(f"Error: {str(e)}", "error")
                
    except Exception as e:
        print_status(f"Failed to initialize: {str(e)}", "error")
        return 1
    finally:
        await cli.shutdown()
        print_status("Chat session ended", "info")
    
    return 0

async def cmd_send(args):
    """Send a single event"""
    print_status(f"Sending {args.type} event")
    
    cli = VextirCLI()
    try:
        await cli.initialize()
        
        # Parse data
        data = {}
        if args.data:
            try:
                data = json.loads(args.data)
            except json.JSONDecodeError:
                data = {"message": args.data}
        
        from lightning_core.abstractions import EventMessage
        event = EventMessage(
            event_type=args.type,
            data=data,
            metadata={
                "source": "vextir_cli",
                "user_id": "cli_user"
            }
        )
        
        if args.wait:
            print_status("Sending event and waiting for response...")
            response = await cli.send_and_wait(event, timeout=args.timeout)
            if response:
                print_status("Response received", "success")
                print(json.dumps(response.data, indent=2))
            else:
                print_status("No response received", "error")
        else:
            await cli.runtime.publish_event(event)
            print_status("Event sent", "success")
            
    except Exception as e:
        print_status(f"Error: {str(e)}", "error")
        return 1
    finally:
        await cli.shutdown()
    
    return 0

async def cmd_monitor(args):
    """Monitor all events in the system"""
    print_header()
    print_status("Starting event monitor")
    print("Press Ctrl+C to stop\n")
    
    cli = VextirCLI()
    try:
        await cli.initialize()
        
        events_seen = []
        
        async def monitor_handler(event):
            events_seen.append(event)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if args.filter and args.filter not in event.event_type:
                return
                
            print(f"{Colors.GRAY}[{timestamp}]{Colors.END} {Colors.CYAN}{event.event_type}{Colors.END}")
            
            if args.verbose:
                print(f"  ID: {event.id}")
                print(f"  Source: {event.metadata.get('source', 'unknown')}")
                if event.data:
                    data_str = json.dumps(event.data, indent=2)[:200]
                    if len(data_str) == 200:
                        data_str += "..."
                    print(f"  Data: {data_str}")
                print()
        
        await cli.runtime.event_bus.subscribe("*", monitor_handler)
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n\nMonitoring stopped")
            print_status(f"Total events seen: {len(events_seen)}", "info")
            
    except Exception as e:
        print_status(f"Error: {str(e)}", "error")
        return 1
    finally:
        await cli.shutdown()
    
    return 0

async def cmd_status(args):
    """Show Vextir OS status"""
    print_header()
    print_status("Checking Vextir OS status...")
    
    try:
        from lightning_core.vextir_os.driver_initialization import initialize_all_drivers
        from lightning_core.vextir_os.drivers import get_driver_registry
        
        # Initialize drivers to check status
        await initialize_all_drivers()
        registry = get_driver_registry()
        
        print(f"\n{Colors.BOLD}Driver Status:{Colors.END}")
        drivers = registry.list_drivers()
        
        running_count = 0
        for driver in drivers:
            status = driver.get('status', 'unknown')
            if status == 'running':
                status_color = Colors.GREEN
                running_count += 1
            elif status == 'error':
                status_color = Colors.RED
            else:
                status_color = Colors.YELLOW
            
            print(f"  • {driver['name']}: {status_color}{status}{Colors.END}")
            if args.verbose and 'capabilities' in driver:
                for cap in driver['capabilities']:
                    print(f"    - {cap}")
        
        print(f"\n{Colors.BOLD}Summary:{Colors.END}")
        print(f"  • Total drivers: {len(drivers)}")
        print(f"  • Running: {running_count}")
        print(f"  • Event bus: {Colors.GREEN}active{Colors.END}")
        
        # Check API key
        if os.environ.get("OPENAI_API_KEY"):
            print(f"  • OpenAI API: {Colors.GREEN}configured{Colors.END}")
        else:
            print(f"  • OpenAI API: {Colors.RED}missing key{Colors.END}")
            
    except Exception as e:
        print_status(f"Error checking status: {str(e)}", "error")
        return 1
    
    return 0

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog='vextir',
        description='Vextir OS - Event-driven AI operating system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vextir chat                           # Interactive chat
  vextir chat --model gpt-4             # Chat with specific model
  vextir send -t system.health          # Send health check event
  vextir send -t llm.chat -d '{"messages":[{"role":"user","content":"Hi"}]}' --wait
  vextir monitor                        # Monitor all events
  vextir monitor --filter llm           # Monitor only LLM events
  vextir status                         # Show system status
        """
    )
    
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Interactive chat session')
    chat_parser.add_argument('--model', help='Model to use (default: gpt-3.5-turbo)')
    chat_parser.add_argument('--temperature', type=float, default=0.7, help='Temperature (default: 0.7)')
    
    # Send command
    send_parser = subparsers.add_parser('send', help='Send an event')
    send_parser.add_argument('-t', '--type', required=True, help='Event type')
    send_parser.add_argument('-d', '--data', help='Event data (JSON string)')
    send_parser.add_argument('--wait', action='store_true', help='Wait for response')
    send_parser.add_argument('--timeout', type=int, default=10, help='Response timeout (default: 10s)')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor system events')
    monitor_parser.add_argument('--filter', help='Filter events by type substring')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to command handlers
    try:
        if args.command == 'chat':
            return asyncio.run(cmd_chat(args))
        elif args.command == 'send':
            return asyncio.run(cmd_send(args))
        elif args.command == 'monitor':
            return asyncio.run(cmd_monitor(args))
        elif args.command == 'status':
            return asyncio.run(cmd_status(args))
    except KeyboardInterrupt:
        print(f"\n{Colors.GRAY}Interrupted{Colors.END}")
        return 0
    except Exception as e:
        print_status(f"Unexpected error: {str(e)}", "error")
        return 1

if __name__ == "__main__":
    sys.exit(main())