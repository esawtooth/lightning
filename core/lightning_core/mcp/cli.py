"""CLI commands for managing MCP servers."""

import click
import yaml
import json
import asyncio
from typing import Optional
from tabulate import tabulate

from .config import MCPConfigLoader
from .registry import MCPRegistry, MCPServerConfig
from .sandbox import SANDBOX_PRESETS
from .client import MCPConnectionType
from ..abstractions.storage import ProviderFactory
from ..abstractions.configuration import RuntimeConfig, ExecutionMode


@click.group(name='mcp')
def mcp_cli():
    """Manage MCP (Model Context Protocol) servers."""
    pass


@mcp_cli.command()
@click.option('--config-dir', help='Configuration directory', default=None)
def list(config_dir: Optional[str]):
    """List all registered MCP servers."""
    asyncio.run(_list_servers(config_dir))


async def _list_servers(config_dir: Optional[str]):
    """List servers implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    # Get all servers
    servers = registry.list_servers()
    
    if not servers:
        click.echo("No MCP servers registered.")
        return
    
    # Format for display
    table_data = []
    for server in servers:
        status = "🟢 Connected" if registry.is_connected(server.id) else "⚪ Disconnected"
        table_data.append([
            server.id,
            server.name,
            server.connection_type.value,
            status,
            ", ".join(server.access_scopes),
            "Yes" if server.auto_start else "No"
        ])
    
    headers = ["ID", "Name", "Type", "Status", "Access Scopes", "Auto Start"]
    click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))


@mcp_cli.command()
@click.argument('server_id')
@click.option('--config-dir', help='Configuration directory', default=None)
def status(server_id: str, config_dir: Optional[str]):
    """Get detailed status of an MCP server."""
    asyncio.run(_get_server_status(server_id, config_dir))


async def _get_server_status(server_id: str, config_dir: Optional[str]):
    """Get server status implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    try:
        status = await registry.get_server_status(server_id)
        
        # Display status
        click.echo(f"\n=== MCP Server: {status['name']} ({status['id']}) ===")
        click.echo(f"Connected: {'Yes' if status['connected'] else 'No'}")
        click.echo(f"Connection Type: {status['connection_type']}")
        click.echo(f"Endpoint: {status['endpoint']}")
        click.echo(f"Access Scopes: {', '.join(status['access_scopes'])}")
        click.echo(f"Auto Start: {'Yes' if status['auto_start'] else 'No'}")
        
        if status['connected']:
            click.echo(f"\nTools ({status.get('tool_count', 0)}):")
            for tool in status.get('tools', []):
                click.echo(f"  - {tool}")
            
            if 'capabilities' in status:
                click.echo("\nCapabilities:")
                for cap in status['capabilities']:
                    click.echo(f"  - {cap['name']} v{cap['version']}")
        
        if 'error' in status:
            click.echo(f"\nError: {status['error']}")
            
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)


@mcp_cli.command()
@click.argument('server_id')
@click.argument('name')
@click.argument('connection_type', type=click.Choice(['sse', 'stdio', 'websocket']))
@click.argument('endpoint')
@click.option('--capabilities', '-c', multiple=True, help='Server capabilities')
@click.option('--scope', '-s', multiple=True, 
              type=click.Choice(['AGENT_CONSEIL', 'AGENT_VEX', 'AGENT_ALL', 'SYSTEM', 'USER']),
              help='Access scopes')
@click.option('--sandbox', type=click.Choice(['strict', 'moderate', 'relaxed', 'disabled']),
              default='moderate', help='Sandbox preset')
@click.option('--auto-start/--no-auto-start', default=False, help='Auto-start server')
@click.option('--config-dir', help='Configuration directory', default=None)
def register(server_id: str, name: str, connection_type: str, endpoint: str,
            capabilities: tuple, scope: tuple, sandbox: str, auto_start: bool,
            config_dir: Optional[str]):
    """Register a new MCP server."""
    asyncio.run(_register_server(
        server_id, name, connection_type, endpoint,
        list(capabilities), list(scope) or ['AGENT_ALL'],
        sandbox, auto_start, config_dir
    ))


async def _register_server(server_id: str, name: str, connection_type: str,
                          endpoint: str, capabilities: list, scopes: list,
                          sandbox: str, auto_start: bool, config_dir: Optional[str]):
    """Register server implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    # Create server config
    server_config = MCPServerConfig(
        id=server_id,
        name=name,
        connection_type=MCPConnectionType(connection_type),
        endpoint=endpoint,
        capabilities=capabilities or [],
        sandbox_config=SANDBOX_PRESETS[sandbox],
        access_scopes=scopes,
        auto_start=auto_start
    )
    
    try:
        # Register with registry
        await registry.register_server(server_config)
        
        # Save to config file
        loader = MCPConfigLoader(config_dir)
        loader.save_server_config(server_config)
        
        click.echo(f"✅ Registered MCP server: {server_id}")
        
        if auto_start:
            click.echo("Attempting to connect...")
            try:
                await registry.connect_server(server_id)
                click.echo("✅ Connected successfully")
            except Exception as e:
                click.echo(f"⚠️  Failed to connect: {e}")
                
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@mcp_cli.command()
@click.argument('server_id')
@click.option('--config-dir', help='Configuration directory', default=None)
def unregister(server_id: str, config_dir: Optional[str]):
    """Unregister an MCP server."""
    asyncio.run(_unregister_server(server_id, config_dir))


async def _unregister_server(server_id: str, config_dir: Optional[str]):
    """Unregister server implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    try:
        # Unregister from registry
        await registry.unregister_server(server_id)
        
        # Remove from config file
        loader = MCPConfigLoader(config_dir)
        loader.remove_server_config(server_id)
        
        click.echo(f"✅ Unregistered MCP server: {server_id}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@mcp_cli.command()
@click.argument('server_id')
@click.option('--config-dir', help='Configuration directory', default=None)
def connect(server_id: str, config_dir: Optional[str]):
    """Connect to an MCP server."""
    asyncio.run(_connect_server(server_id, config_dir))


async def _connect_server(server_id: str, config_dir: Optional[str]):
    """Connect to server implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    try:
        await registry.connect_server(server_id)
        click.echo(f"✅ Connected to MCP server: {server_id}")
        
        # Show available tools
        client = registry.get_client(server_id)
        if client:
            tools = await client.list_tools()
            click.echo(f"\nAvailable tools ({len(tools)}):")
            for tool in tools:
                click.echo(f"  - {tool.name}: {tool.description}")
                
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@mcp_cli.command()
@click.argument('server_id')
@click.option('--config-dir', help='Configuration directory', default=None)
def disconnect(server_id: str, config_dir: Optional[str]):
    """Disconnect from an MCP server."""
    asyncio.run(_disconnect_server(server_id, config_dir))


async def _disconnect_server(server_id: str, config_dir: Optional[str]):
    """Disconnect from server implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    try:
        await registry.disconnect_server(server_id)
        click.echo(f"✅ Disconnected from MCP server: {server_id}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@mcp_cli.command()
@click.argument('server_id')
@click.option('--config-dir', help='Configuration directory', default=None)
def tools(server_id: str, config_dir: Optional[str]):
    """List tools provided by an MCP server."""
    asyncio.run(_list_tools(server_id, config_dir))


async def _list_tools(server_id: str, config_dir: Optional[str]):
    """List tools implementation."""
    # Initialize components
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    storage = ProviderFactory.create_storage_provider(config)
    registry = MCPRegistry(storage)
    await registry.initialize()
    
    # Connect if needed
    if not registry.is_connected(server_id):
        click.echo(f"Connecting to {server_id}...")
        try:
            await registry.connect_server(server_id)
        except Exception as e:
            click.echo(f"❌ Failed to connect: {e}", err=True)
            return
    
    # Get tools
    client = registry.get_client(server_id)
    if not client:
        click.echo("❌ Server not connected", err=True)
        return
    
    try:
        tools = await client.list_tools()
        
        if not tools:
            click.echo("No tools available from this server.")
            return
        
        click.echo(f"\n=== Tools from {server_id} ===\n")
        
        for tool in tools:
            click.echo(f"📦 {tool.name}")
            click.echo(f"   {tool.description}")
            
            if tool.input_schema:
                click.echo("   Parameters:")
                params = tool.input_schema.get('properties', {})
                required = tool.input_schema.get('required', [])
                
                for param, schema in params.items():
                    req_marker = "*" if param in required else ""
                    param_type = schema.get('type', 'any')
                    param_desc = schema.get('description', '')
                    click.echo(f"     - {param}{req_marker} ({param_type}): {param_desc}")
            
            click.echo()
            
    except Exception as e:
        click.echo(f"❌ Error listing tools: {e}", err=True)


@mcp_cli.command()
@click.option('--config-dir', help='Configuration directory', default=None)
def init(config_dir: Optional[str]):
    """Initialize MCP configuration with examples."""
    loader = MCPConfigLoader(config_dir)
    loader.create_example_configs()
    
    click.echo(f"✅ Created example configurations in {loader.config_dir}")
    click.echo("\nNext steps:")
    click.echo("1. Edit servers.yaml to configure your MCP servers")
    click.echo("2. Run 'lightning mcp register' to add servers")
    click.echo("3. Run 'lightning mcp connect <server_id>' to connect")


# Add MCP commands to main CLI
def register_mcp_commands(cli_group):
    """Register MCP commands with the main CLI."""
    cli_group.add_command(mcp_cli)