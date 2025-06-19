"""Example demonstrating MCP server integration with Lightning."""

import asyncio
import logging
from lightning_core.runtime import LightningRuntime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode
from lightning_core.mcp import MCPServerConfig, MCPConnectionType, SANDBOX_PRESETS
from lightning_core.vextir_os.enhanced_agent_driver import EnhancedAgentDriver
from lightning_core.vextir_os.drivers import DriverManifest, DriverType, ResourceSpec

logging.basicConfig(level=logging.INFO)


async def main():
    """Demonstrate MCP server integration."""
    
    # Create runtime
    runtime = LightningRuntime(RuntimeConfig(mode=ExecutionMode.LOCAL))
    
    async with runtime.session():
        # Initialize MCP services
        await runtime.initialize_mcp(load_config=False)
        
        print("=== MCP Server Integration Example ===\n")
        
        # 1. Register an MCP server
        print("1. Registering filesystem MCP server...")
        
        fs_server = MCPServerConfig(
            id="filesystem_demo",
            name="Filesystem Demo Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="npx @modelcontextprotocol/server-filesystem /tmp",
            capabilities=["read", "write", "list"],
            sandbox_config=SANDBOX_PRESETS["strict"],  # Strict sandboxing
            access_scopes=["AGENT_ALL"],
            auto_start=True
        )
        
        await runtime.mcp_registry.register_server(fs_server)
        print("✓ Filesystem server registered\n")
        
        # 2. List registered servers
        print("2. Listing registered MCP servers:")
        servers = runtime.mcp_registry.list_servers()
        for server in servers:
            status = "Connected" if runtime.mcp_registry.is_connected(server.id) else "Disconnected"
            print(f"   - {server.name} ({server.id}): {status}")
        print()
        
        # 3. Connect to the server
        print("3. Connecting to filesystem server...")
        try:
            await runtime.mcp_registry.connect_server("filesystem_demo")
            print("✓ Connected successfully\n")
            
            # Get server status
            status = await runtime.mcp_registry.get_server_status("filesystem_demo")
            print(f"   Tools available: {status.get('tool_count', 0)}")
            for tool in status.get('tools', []):
                print(f"   - {tool}")
            print()
            
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            print("  (This is expected if @modelcontextprotocol/server-filesystem is not installed)")
            print("  To install: npm install -g @modelcontextprotocol/server-filesystem\n")
        
        # 4. Create an enhanced agent with MCP support
        print("4. Creating an agent with MCP support...")
        
        agent_manifest = DriverManifest(
            id="demo_agent",
            name="Demo Agent",
            version="1.0.0",
            author="Lightning",
            description="Agent demonstrating MCP tool usage",
            driver_type=DriverType.AGENT,
            capabilities=["demo.task"],
            resource_requirements=ResourceSpec()
        )
        
        agent = EnhancedAgentDriver(
            manifest=agent_manifest,
            config={
                "model": "gpt-4",
                "system_prompt": "You are a helpful assistant with access to MCP tools."
            },
            mcp_registry=runtime.mcp_registry,
            tool_registry=None  # Could pass Lightning tool registry here
        )
        
        await agent.initialize()
        print("✓ Agent created and initialized\n")
        
        # 5. List available tools for the agent
        print("5. Available tools for the agent:")
        tools = await agent.get_available_tools()
        for tool in tools:
            print(f"   - {tool['name']}: {tool['description']}")
            if 'metadata' in tool and tool['metadata'].get('type') == 'MCP_SERVER':
                print(f"     (From MCP server: {tool['metadata'].get('provider', 'unknown')})")
        print()
        
        # 6. Demonstrate security features
        print("6. Security features:")
        
        # Test rate limiting
        print("   Testing rate limiting...")
        for i in range(3):
            result = await runtime.mcp_security_proxy.validate_tool_call(
                agent_id="demo_agent",
                server_id="filesystem_demo",
                tool_name="read_file",
                parameters={"path": f"/tmp/test{i}.txt"}
            )
            print(f"   - Call {i+1}: {'Allowed' if result.allowed else f'Blocked - {result.reason}'}")
        
        # Test parameter sanitization
        print("\n   Testing parameter sanitization...")
        result = await runtime.mcp_security_proxy.validate_tool_call(
            agent_id="demo_agent",
            server_id="filesystem_demo", 
            tool_name="read_file",
            parameters={
                "path": "/etc/passwd",  # Dangerous path
                "api_key": "secret123"  # Sensitive parameter
            }
        )
        if result.sanitized_parameters:
            print(f"   - Original path: /etc/passwd")
            print(f"   - Sanitized path: {result.sanitized_parameters.get('path', 'N/A')}")
            print(f"   - API key: {result.sanitized_parameters.get('api_key', 'N/A')}")
        print()
        
        # 7. Get statistics
        print("7. MCP usage statistics:")
        stats = await runtime.mcp_security_proxy.get_statistics()
        print(f"   - Total calls: {stats['total_calls']}")
        print(f"   - Blocked calls: {stats['blocked_calls']}")
        print(f"   - Block rate: {stats['block_rate']:.1%}")
        
        # Cleanup
        await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())