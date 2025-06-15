#!/usr/bin/env python3
"""
Vextir OS CLI - Main entry point
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.tree import Tree

# Add the parent directory to the path to import vextir_os modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vextir_cli.config import Config
from vextir_cli.client import VextirClient
from vextir_cli.utils import format_timestamp, format_json, handle_async, get_status_color

console = Console()


@click.group()
@click.option('--config', '-c', help='Configuration file path')
@click.option('--endpoint', '-e', help='Vextir OS endpoint URL')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, config, endpoint, verbose):
    """Vextir OS Command Line Interface
    
    A comprehensive CLI for operating the Vextir AI Operating System.
    Provides access to events, drivers, models, context, and system management.
    """
    ctx.ensure_object(dict)
    
    # Initialize configuration
    config_obj = Config(config_file=config)
    if endpoint:
        config_obj.set('endpoint', endpoint)
    
    ctx.obj['config'] = config_obj
    ctx.obj['verbose'] = verbose
    ctx.obj['client'] = VextirClient(config_obj)


@cli.group()
@click.pass_context
def event(ctx):
    """Event management commands"""
    pass


@event.command('emit')
@click.argument('event_type')
@click.option('--source', '-s', default='cli', help='Event source')
@click.option('--metadata', '-m', help='Event metadata as JSON string')
@click.option('--file', '-f', help='Read metadata from file')
@click.option('--user-id', '-u', help='User ID (defaults to current user)')
@click.pass_context
def emit_event(ctx, event_type, source, metadata, file, user_id):
    """Emit an event to the Vextir OS event bus"""
    
    @handle_async
    async def _emit():
        client = ctx.obj['client']
        
        # Parse metadata
        event_metadata = {}
        if metadata:
            try:
                event_metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON metadata: {e}[/red]")
                return
        
        if file:
            try:
                with open(file, 'r') as f:
                    event_metadata = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                console.print(f"[red]Error reading metadata file: {e}[/red]")
                return
        
        # Get user ID
        current_user_id = user_id
        if not current_user_id:
            current_user_id = await client.get_current_user_id()
        
        # Create and emit event
        event_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'source': source,
            'type': event_type,
            'userID': current_user_id,
            'metadata': event_metadata
        }
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Emitting event...", total=None)
            
            try:
                result = await client.emit_event(event_data)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Event emitted successfully[/green]\n"
                    f"Event ID: {result.get('id', 'N/A')}\n"
                    f"Type: {event_type}\n"
                    f"Source: {source}",
                    title="Event Emitted"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to emit event: {e}[/red]")
    
    _emit()


@event.command('list')
@click.option('--limit', '-l', default=50, help='Number of events to show')
@click.option('--type', '-t', help='Filter by event type')
@click.option('--source', '-s', help='Filter by event source')
@click.option('--user-id', '-u', help='Filter by user ID')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'tree']), default='table', help='Output format')
@click.pass_context
def list_events(ctx, limit, type, source, user_id, format):
    """List recent events from the event bus"""
    
    @handle_async
    async def _list():
        client = ctx.obj['client']
        
        filters = {}
        if type:
            filters['type'] = type
        if source:
            filters['source'] = source
        if user_id:
            filters['user_id'] = user_id
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching events...", total=None)
            
            try:
                events = await client.get_events(limit=limit, filters=filters)
                
                if not events:
                    progress.stop()
                    console.print("[yellow]No events found[/yellow]")
                    return
                
                progress.stop()
                
                if format == 'json':
                    console.print(format_json(events))
                elif format == 'tree':
                    tree = Tree("Events")
                    for event in events:
                        event_node = tree.add(f"[bold]{event['type']}[/bold] ({event['id'][:8]})")
                        event_node.add(f"Source: {event['source']}")
                        event_node.add(f"Time: {format_timestamp(event['timestamp'])}")
                        event_node.add(f"User: {event['userID']}")
                    console.print(tree)
                else:
                    table = Table(title="Recent Events")
                    table.add_column("ID", style="cyan", no_wrap=True)
                    table.add_column("Type", style="magenta")
                    table.add_column("Source", style="green")
                    table.add_column("User", style="blue")
                    table.add_column("Timestamp", style="yellow")
                    
                    for event in events:
                        table.add_row(
                            event['id'][:8] + "...",
                            event['type'],
                            event['source'],
                            event['userID'][:8] + "...",
                            format_timestamp(event['timestamp'])
                        )
                    
                    console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to fetch events: {e}[/red]")
    
    _list()


@event.command('stream')
@click.option('--type', '-t', help='Filter by event type')
@click.option('--source', '-s', help='Filter by event source')
@click.option('--user-id', '-u', help='Filter by user ID')
@click.pass_context
def stream_events(ctx, type, source, user_id):
    """Stream events in real-time"""
    
    @handle_async
    async def _stream():
        client = ctx.obj['client']
        
        filters = {}
        if type:
            filters['type'] = type
        if source:
            filters['source'] = source
        if user_id:
            filters['user_id'] = user_id
        
        console.print("[green]Streaming events... Press Ctrl+C to stop[/green]")
        
        try:
            async for event in client.stream_events(filters=filters):
                console.print(Panel(
                    f"[bold]{event['type']}[/bold]\n"
                    f"ID: {event['id']}\n"
                    f"Source: {event['source']}\n"
                    f"User: {event['userID']}\n"
                    f"Time: {format_timestamp(event['timestamp'])}\n"
                    f"Metadata: {format_json(event.get('metadata', {}), compact=True)}",
                    title=f"Event: {event['type']}"
                ))
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Stream stopped[/yellow]")
        except Exception as e:
            console.print(f"[red]Stream error: {e}[/red]")
    
    _stream()


@cli.group()
@click.pass_context
def driver(ctx):
    """Driver management commands"""
    pass


@driver.command('list')
@click.option('--type', '-t', help='Filter by driver type')
@click.option('--status', '-s', help='Filter by status')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_drivers(ctx, type, status, format):
    """List registered drivers"""
    
    @handle_async
    async def _list():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching drivers...", total=None)
            
            try:
                drivers = await client.get_drivers()
                
                # Apply filters
                if type:
                    drivers = [d for d in drivers if d.get('type') == type]
                if status:
                    drivers = [d for d in drivers if d.get('status') == status]
                
                if not drivers:
                    progress.stop()
                    console.print("[yellow]No drivers found[/yellow]")
                    return
                
                progress.stop()
                
                if format == 'json':
                    console.print(format_json(drivers))
                else:
                    table = Table(title="Registered Drivers")
                    table.add_column("ID", style="cyan")
                    table.add_column("Name", style="magenta")
                    table.add_column("Type", style="green")
                    table.add_column("Status", style="blue")
                    table.add_column("Capabilities", style="yellow")
                    table.add_column("Events", style="red")
                    
                    for driver in drivers:
                        capabilities = ", ".join(driver.get('capabilities', [])[:3])
                        if len(driver.get('capabilities', [])) > 3:
                            capabilities += "..."
                        
                        status_color = {
                            'running': '[green]running[/green]',
                            'stopped': '[red]stopped[/red]',
                            'error': '[red]error[/red]',
                            'starting': '[yellow]starting[/yellow]'
                        }.get(driver.get('status', 'unknown'), driver.get('status', 'unknown'))
                        
                        table.add_row(
                            driver['id'],
                            driver['name'],
                            driver['type'],
                            status_color,
                            capabilities,
                            str(driver.get('event_count', 0))
                        )
                    
                    console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to fetch drivers: {e}[/red]")
    
    _list()


@driver.command('start')
@click.argument('driver_id')
@click.option('--config', '-c', help='Driver configuration as JSON')
@click.pass_context
def start_driver(ctx, driver_id, config):
    """Start a driver"""
    
    @handle_async
    async def _start():
        client = ctx.obj['client']
        
        driver_config = {}
        if config:
            try:
                driver_config = json.loads(config)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON config: {e}[/red]")
                return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Starting driver {driver_id}...", total=None)
            
            try:
                result = await client.start_driver(driver_id, driver_config)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Driver started successfully[/green]\n"
                    f"Driver ID: {driver_id}\n"
                    f"Status: {result.get('status', 'unknown')}",
                    title="Driver Started"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to start driver: {e}[/red]")
    
    _start()


@driver.command('stop')
@click.argument('driver_id')
@click.pass_context
def stop_driver(ctx, driver_id):
    """Stop a driver"""
    
    @handle_async
    async def _stop():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Stopping driver {driver_id}...", total=None)
            
            try:
                await client.stop_driver(driver_id)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Driver stopped successfully[/green]\n"
                    f"Driver ID: {driver_id}",
                    title="Driver Stopped"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to stop driver: {e}[/red]")
    
    _stop()


@driver.command('status')
@click.argument('driver_id')
@click.pass_context
def driver_status(ctx, driver_id):
    """Get detailed driver status"""
    
    @handle_async
    async def _status():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Getting driver status...", total=None)
            
            try:
                status = await client.get_driver_status(driver_id)
                progress.update(task, completed=True)
                
                if not status:
                    console.print(f"[red]Driver {driver_id} not found[/red]")
                    return
                
                console.print(Panel(
                    f"[bold]Driver Status[/bold]\n\n"
                    f"ID: {status['id']}\n"
                    f"Name: {status['name']}\n"
                    f"Type: {status['type']}\n"
                    f"Status: {status['status']}\n"
                    f"Events Processed: {status.get('event_count', 0)}\n"
                    f"Last Activity: {format_timestamp(status.get('last_activity')) if status.get('last_activity') else 'Never'}\n"
                    f"Capabilities: {', '.join(status.get('capabilities', []))}\n"
                    f"Error: {status.get('error_message', 'None')}",
                    title=f"Driver: {driver_id}"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to get driver status: {e}[/red]")
    
    _status()


@cli.group()
@click.pass_context
def model(ctx):
    """Model management commands"""
    pass


@model.command('list')
@click.option('--provider', '-p', help='Filter by provider')
@click.option('--capability', '-c', help='Filter by capability')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_models(ctx, provider, capability, format):
    """List available AI models"""
    
    @handle_async
    async def _list():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching models...", total=None)
            
            try:
                models = await client.get_models()
                progress.update(task, completed=True)
                
                # Apply filters
                if provider:
                    models = [m for m in models if m.get('provider') == provider]
                if capability:
                    models = [m for m in models if capability in m.get('capabilities', [])]
                
                if not models:
                    console.print("[yellow]No models found[/yellow]")
                    return
                
                if format == 'json':
                    console.print(format_json(models))
                else:
                    table = Table(title="Available Models")
                    table.add_column("ID", style="cyan")
                    table.add_column("Name", style="magenta")
                    table.add_column("Provider", style="green")
                    table.add_column("Capabilities", style="blue")
                    table.add_column("Context", style="yellow")
                    table.add_column("Cost (Input/Output)", style="red")
                    
                    for model in models:
                        capabilities = ", ".join(model.get('capabilities', [])[:2])
                        if len(model.get('capabilities', [])) > 2:
                            capabilities += "..."
                        
                        cost = model.get('cost_per_1k_tokens', {})
                        cost_str = f"${cost.get('input', 0):.3f}/${cost.get('output', 0):.3f}"
                        
                        table.add_row(
                            model['id'],
                            model['name'],
                            model['provider'],
                            capabilities,
                            f"{model.get('context_window', 0):,}",
                            cost_str
                        )
                    
                    console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to fetch models: {e}[/red]")
    
    _list()


@model.command('info')
@click.argument('model_id')
@click.pass_context
def model_info(ctx, model_id):
    """Get detailed model information"""
    
    @handle_async
    async def _info():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Getting model info...", total=None)
            
            try:
                model = await client.get_model_info(model_id)
                progress.update(task, completed=True)
                
                if not model:
                    console.print(f"[red]Model {model_id} not found[/red]")
                    return
                
                cost = model.get('cost_per_1k_tokens', {})
                
                console.print(Panel(
                    f"[bold]Model Information[/bold]\n\n"
                    f"ID: {model['id']}\n"
                    f"Name: {model['name']}\n"
                    f"Provider: {model['provider']}\n"
                    f"Capabilities: {', '.join(model.get('capabilities', []))}\n"
                    f"Context Window: {model.get('context_window', 0):,} tokens\n"
                    f"Max Output: {model.get('max_output_tokens', 0):,} tokens\n"
                    f"Cost per 1K tokens:\n"
                    f"  Input: ${cost.get('input', 0):.4f}\n"
                    f"  Output: ${cost.get('output', 0):.4f}\n"
                    f"Streaming: {'Yes' if model.get('supports_streaming', False) else 'No'}\n"
                    f"Enabled: {'Yes' if model.get('enabled', False) else 'No'}",
                    title=f"Model: {model_id}"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to get model info: {e}[/red]")
    
    _info()


@cli.group()
@click.pass_context
def tool(ctx):
    """Tool management commands"""
    pass


@tool.command('list')
@click.option('--type', '-t', help='Filter by tool type')
@click.option('--capability', '-c', help='Filter by capability')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_tools(ctx, type, capability, format):
    """List available tools"""
    
    @handle_async
    async def _list():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching tools...", total=None)
            
            try:
                tools = await client.get_tools()
                progress.update(task, completed=True)
                
                # Apply filters
                if type:
                    tools = [t for t in tools if t.get('tool_type') == type]
                if capability:
                    tools = [t for t in tools if capability in t.get('capabilities', [])]
                
                if not tools:
                    console.print("[yellow]No tools found[/yellow]")
                    return
                
                if format == 'json':
                    console.print(format_json(tools))
                else:
                    table = Table(title="Available Tools")
                    table.add_column("ID", style="cyan")
                    table.add_column("Name", style="magenta")
                    table.add_column("Type", style="green")
                    table.add_column("Description", style="blue")
                    table.add_column("Capabilities", style="yellow")
                    table.add_column("Status", style="red")
                    
                    for tool in tools:
                        capabilities = ", ".join(tool.get('capabilities', [])[:2])
                        if len(tool.get('capabilities', [])) > 2:
                            capabilities += "..."
                        
                        status = "[green]enabled[/green]" if tool.get('enabled', False) else "[red]disabled[/red]"
                        
                        table.add_row(
                            tool['id'],
                            tool['name'],
                            tool['tool_type'],
                            tool.get('description', '')[:50] + "..." if len(tool.get('description', '')) > 50 else tool.get('description', ''),
                            capabilities,
                            status
                        )
                    
                    console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to fetch tools: {e}[/red]")
    
    _list()


@cli.group()
@click.pass_context
def context(ctx):
    """Context hub operations"""
    pass


@context.command('read')
@click.argument('path')
@click.pass_context
def context_read(ctx, path):
    """Read from context hub"""
    
    @handle_async
    async def _read():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Reading {path}...", total=None)
            
            try:
                result = await client.context_read(path)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[bold]Content[/bold]\n\n{result.get('content', '')}\n\n"
                    f"[bold]Metadata[/bold]\n{format_json(result.get('metadata', {}), compact=True)}",
                    title=f"Context: {path}"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to read context: {e}[/red]")
    
    _read()


@context.command('write')
@click.argument('path')
@click.argument('content')
@click.option('--metadata', '-m', help='Metadata as JSON string')
@click.pass_context
def context_write(ctx, path, content, metadata):
    """Write to context hub"""
    
    @handle_async
    async def _write():
        client = ctx.obj['client']
        
        # Parse metadata
        meta = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON metadata: {e}[/red]")
                return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Writing to {path}...", total=None)
            
            try:
                result = await client.context_write(path, content, meta)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Successfully wrote to context[/green]\n"
                    f"Path: {path}\n"
                    f"Timestamp: {result.get('timestamp', 'N/A')}",
                    title="Context Written"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to write context: {e}[/red]")
    
    _write()


@context.command('query')
@click.argument('query')
@click.option('--limit', '-l', default=10, help='Maximum results')
@click.pass_context
def context_query(ctx, query, limit):
    """Query context hub with SQL"""
    
    @handle_async
    async def _query():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Querying context...", total=None)
            
            try:
                results = await client.context_query(query, limit)
                progress.update(task, completed=True)
                
                if not results:
                    console.print("[yellow]No results found[/yellow]")
                    return
                
                table = Table(title="Query Results")
                table.add_column("Path", style="cyan")
                table.add_column("Content", style="magenta")
                table.add_column("Score", style="green")
                
                for result in results:
                    content = result.get('content', '')
                    if len(content) > 100:
                        content = content[:97] + "..."
                    
                    table.add_row(
                        result.get('path', ''),
                        content,
                        f"{result.get('score', 0):.2f}"
                    )
                
                console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to query context: {e}[/red]")
    
    _query()


@cli.group()
@click.pass_context
def instruction(ctx):
    """Instruction management commands"""
    pass


@instruction.command('list')
@click.option('--status', '-s', help='Filter by status')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_instructions(ctx, status, format):
    """List user instructions"""
    
    @handle_async
    async def _list():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching instructions...", total=None)
            
            try:
                instructions = await client.get_instructions()
                progress.update(task, completed=True)
                
                # Apply filters
                if status:
                    instructions = [i for i in instructions if i.get('status') == status]
                
                if not instructions:
                    console.print("[yellow]No instructions found[/yellow]")
                    return
                
                if format == 'json':
                    console.print(format_json(instructions))
                else:
                    table = Table(title="User Instructions")
                    table.add_column("ID", style="cyan")
                    table.add_column("Name", style="magenta")
                    table.add_column("Description", style="blue")
                    table.add_column("Status", style="green")
                    table.add_column("Last Run", style="yellow")
                    
                    for instruction in instructions:
                        status_color = {
                            'active': '[green]active[/green]',
                            'inactive': '[red]inactive[/red]',
                            'error': '[red]error[/red]'
                        }.get(instruction.get('status', 'unknown'), instruction.get('status', 'unknown'))
                        
                        table.add_row(
                            instruction['id'],
                            instruction['name'],
                            instruction.get('description', '')[:50] + "..." if len(instruction.get('description', '')) > 50 else instruction.get('description', ''),
                            status_color,
                            format_timestamp(instruction.get('last_run'))
                        )
                    
                    console.print(table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to fetch instructions: {e}[/red]")
    
    _list()


@instruction.command('execute')
@click.argument('instruction_id')
@click.pass_context
def execute_instruction(ctx, instruction_id):
    """Execute an instruction"""
    
    @handle_async
    async def _execute():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Executing instruction {instruction_id}...", total=None)
            
            try:
                result = await client.execute_instruction(instruction_id)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Instruction execution started[/green]\n"
                    f"Instruction ID: {instruction_id}\n"
                    f"Execution ID: {result.get('execution_id', 'N/A')}\n"
                    f"Status: {result.get('status', 'unknown')}\n"
                    f"Started: {format_timestamp(result.get('timestamp'))}",
                    title="Instruction Executed"
                ))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to execute instruction: {e}[/red]")
    
    _execute()


@cli.group()
@click.pass_context
def system(ctx):
    """System management commands"""
    pass


@system.command('status')
@click.pass_context
def system_status(ctx):
    """Get system status and health"""
    
    @handle_async
    async def _status():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Getting system status...", total=None)
            
            try:
                status = await client.get_system_status()
                progress.update(task, completed=True)
                
                # Create components table
                components_table = Table(title="System Components")
                components_table.add_column("Component", style="cyan")
                components_table.add_column("Status", style="green")
                
                for component, comp_status in status.get('components', {}).items():
                    status_color = get_status_color(comp_status)
                    components_table.add_row(
                        component.replace('_', ' ').title(),
                        f"[{status_color}]{comp_status}[/{status_color}]"
                    )
                
                # Create metrics table
                metrics_table = Table(title="System Metrics")
                metrics_table.add_column("Metric", style="cyan")
                metrics_table.add_column("Value", style="yellow")
                
                for metric, value in status.get('metrics', {}).items():
                    metrics_table.add_row(
                        metric.replace('_', ' ').title(),
                        str(value)
                    )
                
                overall_status = status.get('status', 'unknown')
                status_color = get_status_color(overall_status)
                
                console.print(Panel(
                    f"[bold]System Status: [{status_color}]{overall_status.upper()}[/{status_color}][/bold]\n"
                    f"Version: {status.get('version', 'unknown')}\n"
                    f"Uptime: {status.get('uptime', 'unknown')}",
                    title="Vextir OS System Status"
                ))
                
                console.print(components_table)
                console.print(metrics_table)
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to get system status: {e}[/red]")
    
    _status()


@system.command('metrics')
@click.pass_context
def system_metrics(ctx):
    """Get detailed system metrics"""
    
    @handle_async
    async def _metrics():
        client = ctx.obj['client']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Getting system metrics...", total=None)
            
            try:
                metrics = await client.get_system_metrics()
                progress.update(task, completed=True)
                
                console.print(format_json(metrics))
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to get system metrics: {e}[/red]")
    
    _metrics()


@cli.group()
@click.pass_context
def auth(ctx):
    """Authentication commands"""
    pass


@auth.command('login')
@click.pass_context
def login_user(ctx):
    """Login using Azure CLI authentication"""
    
    @handle_async
    async def _login():
        config_obj = ctx.obj['config']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Checking Azure CLI authentication...", total=None)
            
            try:
                # Check if Azure CLI is logged in
                import subprocess
                result = subprocess.run(
                    ['az', 'account', 'show', '--query', 'user.name', '-o', 'tsv'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                username = result.stdout.strip()
                progress.stop()
                
                console.print(Panel(
                    f"[green]Azure CLI authentication verified[/green]\n"
                    f"Logged in as: {username}\n"
                    f"Authentication method: Azure CLI",
                    title="Authentication Status"
                ))
                
                # Update config
                config_obj.set('auth.method', 'azure_cli')
                config_obj.set('auth.username', username)
                
            except subprocess.CalledProcessError:
                progress.stop()
                console.print(f"[red]Azure CLI not logged in. Please run 'az login' first.[/red]")
            except FileNotFoundError:
                progress.stop()
                console.print(f"[red]Azure CLI not found. Please install Azure CLI first.[/red]")
            except Exception as e:
                progress.stop()
                console.print(f"[red]Authentication check failed: {e}[/red]")
    
    _login()


@auth.command('whoami')
@click.pass_context
def whoami(ctx):
    """Show current Azure CLI user information"""
    
    @handle_async
    async def _whoami():
        config_obj = ctx.obj['config']
        
        try:
            # Get Azure CLI user info
            import subprocess
            
            # Get user name
            user_result = subprocess.run(
                ['az', 'account', 'show', '--query', 'user.name', '-o', 'tsv'],
                capture_output=True,
                text=True,
                check=True
            )
            username = user_result.stdout.strip()
            
            # Get subscription info
            sub_result = subprocess.run(
                ['az', 'account', 'show', '--query', '{name:name,id:id,tenantId:tenantId}', '-o', 'json'],
                capture_output=True,
                text=True,
                check=True
            )
            sub_info = json.loads(sub_result.stdout)
            
            console.print(Panel(
                f"[bold]Current Azure CLI User[/bold]\n\n"
                f"Username: {username}\n"
                f"Subscription: {sub_info.get('name', 'N/A')}\n"
                f"Subscription ID: {sub_info.get('id', 'N/A')}\n"
                f"Tenant ID: {sub_info.get('tenantId', 'N/A')}\n"
                f"Auth Method: Azure CLI\n"
                f"Vextir Endpoint: {config_obj.get('endpoint', 'Not configured')}",
                title="Authentication Information"
            ))
            
        except subprocess.CalledProcessError:
            console.print(f"[red]Azure CLI not logged in. Please run 'az login' first.[/red]")
        except FileNotFoundError:
            console.print(f"[red]Azure CLI not found. Please install Azure CLI first.[/red]")
        except Exception as e:
            console.print(f"[red]Failed to get user info: {e}[/red]")
    
    _whoami()


@cli.group()
@click.pass_context
def hub(ctx):
    """Context Hub operations (integrated CLI access)"""
    pass


def get_hub_config(ctx):
    """Get Context Hub configuration with auto-setup"""
    config_obj = ctx.obj['config']
    
    # Auto-configure Context Hub endpoint if not set
    hub_endpoint = config_obj.get('context_hub.endpoint')
    if not hub_endpoint:
        # Use the same endpoint as the main Vextir OS but with context hub path
        main_endpoint = config_obj.get('endpoint', 'https://test-vextir.azurewebsites.net')
        hub_endpoint = f"{main_endpoint}/api/context-hub"
        config_obj.set('context_hub.endpoint', hub_endpoint)
    
    # Get current user from Azure CLI
    try:
        import subprocess
        result = subprocess.run(
            ['az', 'account', 'show', '--query', 'user.name', '-o', 'tsv'],
            capture_output=True,
            text=True,
            check=True
        )
        username = result.stdout.strip()
        config_obj.set('auth.username', username)
    except:
        username = config_obj.get('auth.username', 'default')
    
    return hub_endpoint, username


def execute_contexthub_cli(ctx, cmd_args, **kwargs):
    """Execute contexthub-cli with proper environment setup"""
    hub_endpoint, username = get_hub_config(ctx)
    
    import subprocess
    import sys
    
    # Build command
    cmd = [sys.executable, "context-hub/contexthub-cli.py"] + cmd_args
    
    # Set environment variables
    env = {
        **os.environ,
        'CONTEXT_HUB_URL': hub_endpoint,
        'CONTEXT_HUB_USER': username
    }
    
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, **kwargs)
        
        if result.returncode == 0:
            if result.stdout:
                console.print(result.stdout)
        else:
            console.print(f"[red]Command failed: {result.stderr}[/red]")
            return False
        
        return True
        
    except Exception as e:
        console.print(f"[red]Failed to execute command: {e}[/red]")
        return False


@hub.command('init')
@click.pass_context
def hub_init(ctx):
    """Initialize user's Context Hub store"""
    
    @handle_async
    async def _init():
        client = ctx.obj['client']
        hub_endpoint, username = get_hub_config(ctx)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Initializing Context Hub store...", total=None)
            
            try:
                # Create user's personal store
                result = await client.init_user_context_store(username)
                progress.update(task, completed=True)
                
                console.print(Panel(
                    f"[green]Context Hub store initialized successfully[/green]\n"
                    f"User: {username}\n"
                    f"Store ID: {result.get('store_id', 'N/A')}\n"
                    f"Endpoint: {hub_endpoint}",
                    title="Context Hub Initialized"
                ))
                
                # Set up initial folders
                execute_contexthub_cli(ctx, ['new', 'projects', '--folder'])
                execute_contexthub_cli(ctx, ['new', 'documents', '--folder'])
                execute_contexthub_cli(ctx, ['new', 'notes', '--folder'])
                
                console.print("\n[green]Created initial folder structure:[/green]")
                console.print("  📁 projects/")
                console.print("  📁 documents/")
                console.print("  📁 notes/")
                
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]Failed to initialize Context Hub: {e}[/red]")
    
    _init()


@hub.command('status')
@click.argument('local_path', required=False, default='.')
@click.pass_context
def hub_status(ctx, local_path):
    """Show Context Hub status and sync information"""
    
    # Check if this is a local sync status or general hub status
    if local_path != '.' and Path(local_path).exists():
        execute_contexthub_cli(ctx, ['sync-status', local_path])
    else:
        # Show general Context Hub status
        execute_contexthub_cli(ctx, ['status'])


@hub.command('ls')
@click.argument('path', default='')
@click.pass_context
def hub_ls(ctx, path):
    """List contents of a Context Hub folder"""
    execute_contexthub_cli(ctx, ['ls', path] if path else ['ls'])


@hub.command('cat')
@click.argument('path')
@click.pass_context
def hub_cat(ctx, path):
    """Show content of a Context Hub document"""
    execute_contexthub_cli(ctx, ['cat', path])


@hub.command('cd')
@click.argument('path')
@click.pass_context
def hub_cd(ctx, path):
    """Change current workspace directory"""
    execute_contexthub_cli(ctx, ['cd', path])


@hub.command('pwd')
@click.pass_context
def hub_pwd(ctx):
    """Show current workspace directory"""
    execute_contexthub_cli(ctx, ['pwd'])


@hub.command('new')
@click.argument('name')
@click.option('--folder', '-d', is_flag=True, help='Create a folder')
@click.option('--content', '-c', default='', help='Initial content for file')
@click.pass_context
def hub_new(ctx, name, folder, content):
    """Create a new file or folder in Context Hub"""
    cmd = ['new', name]
    if folder:
        cmd.append('--folder')
    if content:
        cmd.extend(['--content', content])
    
    execute_contexthub_cli(ctx, cmd)


@hub.command('rm')
@click.argument('path')
@click.pass_context
def hub_rm(ctx, path):
    """Remove a file or folder from Context Hub"""
    execute_contexthub_cli(ctx, ['rm', path])


@hub.command('mv')
@click.argument('source')
@click.argument('dest')
@click.pass_context
def hub_mv(ctx, source, dest):
    """Move or rename a file/folder in Context Hub"""
    execute_contexthub_cli(ctx, ['mv', source, dest])


@hub.command('search')
@click.argument('query')
@click.option('--limit', '-n', default=10, help='Maximum results')
@click.pass_context
def hub_search(ctx, query, limit):
    """Search for content across Context Hub"""
    execute_contexthub_cli(ctx, ['search', query, '--limit', str(limit)])


@hub.command('pull')
@click.argument('hub_path')
@click.argument('local_path')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing local directory')
@click.pass_context
def hub_pull(ctx, hub_path, local_path, force):
    """Pull Context Hub folder to local filesystem for editing"""
    cmd = ['pull', hub_path, local_path]
    if force:
        cmd.append('--force')
    
    execute_contexthub_cli(ctx, cmd)


@hub.command('push')
@click.argument('local_path')
@click.argument('hub_path', required=False)
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be changed without uploading')
@click.option('--no-confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def hub_push(ctx, local_path, hub_path, dry_run, no_confirm):
    """Push local changes back to Context Hub"""
    cmd = ['push', local_path]
    if hub_path:
        cmd.append(hub_path)
    if dry_run:
        cmd.append('--dry-run')
    if no_confirm:
        cmd.append('--no-confirm')
    
    execute_contexthub_cli(ctx, cmd)


@hub.command('share')
@click.argument('path')
@click.argument('user')
@click.option('--write', '-w', is_flag=True, help='Grant write access')
@click.pass_context
def hub_share(ctx, path, user, write):
    """Share a folder with another user"""
    cmd = ['share', path, user]
    if write:
        cmd.append('--write')
    
    execute_contexthub_cli(ctx, cmd)


@hub.command('shared')
@click.pass_context
def hub_shared(ctx):
    """Show all shared folders and their permissions"""
    execute_contexthub_cli(ctx, ['shared'])


@hub.command('auto-sync')
@click.argument('local_path')
@click.option('--interval', '-i', default=5, help='Watch interval in seconds')
@click.pass_context
def hub_auto_sync(ctx, local_path, interval):
    """Auto-sync local directory with Context Hub"""
    execute_contexthub_cli(ctx, ['auto-sync', local_path, '--interval', str(interval)])


@hub.group()
@click.pass_context
def config(ctx):
    """Context Hub configuration management"""
    pass


@config.command('show')
@click.pass_context
def hub_config_show(ctx):
    """Show Context Hub configuration"""
    execute_contexthub_cli(ctx, ['config', 'show'])


@config.command('set')
@click.argument('setting')
@click.argument('value')
@click.pass_context
def hub_config_set(ctx, setting, value):
    """Set Context Hub configuration"""
    execute_contexthub_cli(ctx, ['config', 'set', setting, value])


@config.command('reset')
@click.pass_context
def hub_config_reset(ctx):
    """Reset Context Hub configuration"""
    execute_contexthub_cli(ctx, ['config', 'reset'])


@cli.group()
@click.pass_context
def config(ctx):
    """Configuration management commands"""
    pass


@config.command('get')
@click.argument('key', required=False)
@click.pass_context
def config_get(ctx, key):
    """Get configuration value(s)"""
    config_obj = ctx.obj['config']
    
    if key:
        value = config_obj.get(key)
        if value is not None:
            if isinstance(value, (dict, list)):
                console.print(format_json(value))
            else:
                console.print(str(value))
        else:
            console.print(f"[red]Configuration key '{key}' not found[/red]")
    else:
        # Show all configuration
        all_config = config_obj.list_keys()
        console.print(format_json(all_config))


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value"""
    config_obj = ctx.obj['config']
    
    # Try to parse as JSON first, fallback to string
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value
    
    config_obj.set(key, parsed_value)
    console.print(f"[green]Set {key} = {parsed_value}[/green]")


@config.command('delete')
@click.argument('key')
@click.pass_context
def config_delete(ctx, key):
    """Delete configuration key"""
    config_obj = ctx.obj['config']
    
    if config_obj.delete(key):
        console.print(f"[green]Deleted configuration key '{key}'[/green]")
    else:
        console.print(f"[red]Configuration key '{key}' not found[/red]")


@config.command('reset')
@click.pass_context
def config_reset(ctx):
    """Reset configuration to defaults"""
    config_obj = ctx.obj['config']
    
    if Confirm.ask("Are you sure you want to reset all configuration to defaults?"):
        config_obj.reset()
        console.print("[green]Configuration reset to defaults[/green]")
    else:
        console.print("[yellow]Reset cancelled[/yellow]")


if __name__ == '__main__':
    cli()
