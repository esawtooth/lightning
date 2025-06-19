"""MCP Driver for handling MCP-related events in VextirOS."""

import asyncio
import json
from typing import Any, Dict, List, Optional
import logging

from ...vextir_os.drivers.tool_driver import ToolDriver
from ...vextir_os.models import VextirEvent
from ..registry import MCPRegistry, MCPServerConfig
from ..proxy import MCPSecurityProxy, ValidationResult
from ..sandbox import MCPSandbox
from ..client import MCPClient, MCPTool

logger = logging.getLogger(__name__)


class MCPDriver(ToolDriver):
    """Driver that manages MCP server connections and tool execution."""
    
    driver_type = "mcp"
    
    def __init__(self, 
                 mcp_registry: MCPRegistry,
                 security_proxy: MCPSecurityProxy,
                 mcp_sandbox: MCPSandbox):
        super().__init__()
        self.mcp_registry = mcp_registry
        self.security_proxy = security_proxy
        self.mcp_sandbox = mcp_sandbox
        self._connection_tasks: Dict[str, asyncio.Task] = {}
        
    async def initialize(self) -> None:
        """Initialize the MCP driver."""
        await super().initialize()
        await self.mcp_registry.initialize()
        
        # Start auto-connect servers
        servers = self.mcp_registry.list_servers()
        for server in servers:
            if server.auto_start:
                asyncio.create_task(self._auto_connect_server(server))
    
    async def shutdown(self) -> None:
        """Shutdown the MCP driver."""
        # Cancel all connection tasks
        for task in self._connection_tasks.values():
            task.cancel()
        
        # Disconnect all servers
        for server in self.mcp_registry.list_servers():
            if self.mcp_registry.is_connected(server.id):
                await self.mcp_registry.disconnect_server(server.id)
        
        # Cleanup sandboxes
        await self.mcp_sandbox.cleanup_all()
        
        await super().shutdown()
    
    def can_handle(self, event: VextirEvent) -> bool:
        """Check if this driver can handle the event."""
        return event.event_type.startswith("mcp.")
    
    async def handle_event(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle MCP-related events."""
        try:
            if event.event_type == "mcp.tool.execute":
                return await self._handle_tool_execute(event)
            elif event.event_type == "mcp.server.connect":
                return await self._handle_server_connect(event)
            elif event.event_type == "mcp.server.disconnect":
                return await self._handle_server_disconnect(event)
            elif event.event_type == "mcp.server.register":
                return await self._handle_server_register(event)
            elif event.event_type == "mcp.server.list":
                return await self._handle_server_list(event)
            elif event.event_type == "mcp.server.status":
                return await self._handle_server_status(event)
            elif event.event_type == "mcp.tool.list":
                return await self._handle_tool_list(event)
            else:
                logger.warning(f"Unhandled MCP event type: {event.event_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error handling MCP event: {e}")
            return VextirEvent(
                event_type="mcp.error",
                event_category="OUTPUT",
                data={
                    "original_event": event.event_type,
                    "error": str(e),
                    "agent_id": event.agent_id,
                }
            )
    
    async def _handle_tool_execute(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle tool execution request."""
        data = event.data
        agent_id = event.agent_id or "unknown"
        server_id = data.get("server_id")
        tool_name = data.get("tool_name")
        parameters = data.get("parameters", {})
        
        if not server_id or not tool_name:
            return VextirEvent(
                event_type="mcp.tool.error",
                event_category="OUTPUT",
                data={
                    "error": "Missing server_id or tool_name",
                    "agent_id": agent_id,
                }
            )
        
        # Validate the tool call
        validation_result = await self.security_proxy.validate_tool_call(
            agent_id=agent_id,
            server_id=server_id,
            tool_name=tool_name,
            parameters=parameters,
            context=event.context
        )
        
        if not validation_result.allowed:
            logger.warning(
                f"MCP tool call blocked: agent={agent_id}, server={server_id}, "
                f"tool={tool_name}, reason={validation_result.reason}"
            )
            return VextirEvent(
                event_type="mcp.tool.blocked",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "reason": validation_result.reason,
                    "agent_id": agent_id,
                }
            )
        
        # Get the MCP client
        client = self.mcp_registry.get_client(server_id)
        if not client:
            # Try to connect if not connected
            await self.mcp_registry.connect_server(server_id)
            client = self.mcp_registry.get_client(server_id)
            
            if not client:
                return VextirEvent(
                    event_type="mcp.tool.error",
                    event_category="OUTPUT",
                    data={
                        "error": f"Server {server_id} not connected",
                        "agent_id": agent_id,
                    }
                )
        
        # Execute the tool with sanitized parameters
        try:
            result = await client.execute_tool(
                tool_name,
                validation_result.sanitized_parameters or parameters
            )
            
            return VextirEvent(
                event_type="mcp.tool.result",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "result": result,
                    "agent_id": agent_id,
                }
            )
            
        except Exception as e:
            logger.error(f"Error executing MCP tool: {e}")
            return VextirEvent(
                event_type="mcp.tool.error",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "error": str(e),
                    "agent_id": agent_id,
                }
            )
    
    async def _handle_server_connect(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle server connection request."""
        server_id = event.data.get("server_id")
        if not server_id:
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={"error": "Missing server_id"}
            )
        
        try:
            # Get server config
            server = await self.mcp_registry.get_server(server_id)
            if not server:
                return VextirEvent(
                    event_type="mcp.server.error",
                    event_category="OUTPUT",
                    data={"error": f"Server {server_id} not found"}
                )
            
            # Create sandbox if needed
            if server.sandbox_config.enabled:
                await self.mcp_sandbox.create_environment(server_id, server.sandbox_config)
            
            # Connect to server
            await self.mcp_registry.connect_server(server_id)
            
            # Get available tools
            client = self.mcp_registry.get_client(server_id)
            tools = await client.list_tools()
            
            return VextirEvent(
                event_type="mcp.server.connected",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "server_name": server.name,
                    "tool_count": len(tools),
                    "tools": [{"name": t.name, "description": t.description} for t in tools]
                }
            )
            
        except Exception as e:
            logger.error(f"Error connecting to MCP server: {e}")
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "error": str(e)
                }
            )
    
    async def _handle_server_disconnect(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle server disconnection request."""
        server_id = event.data.get("server_id")
        if not server_id:
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={"error": "Missing server_id"}
            )
        
        try:
            # Disconnect server
            await self.mcp_registry.disconnect_server(server_id)
            
            # Cleanup sandbox
            await self.mcp_sandbox.destroy_environment(server_id)
            
            return VextirEvent(
                event_type="mcp.server.disconnected",
                event_category="OUTPUT",
                data={"server_id": server_id}
            )
            
        except Exception as e:
            logger.error(f"Error disconnecting MCP server: {e}")
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "error": str(e)
                }
            )
    
    async def _handle_server_register(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle server registration request."""
        try:
            config_data = event.data.get("config")
            if not config_data:
                return VextirEvent(
                    event_type="mcp.server.error",
                    event_category="OUTPUT",
                    data={"error": "Missing server configuration"}
                )
            
            # Create server config
            config = MCPServerConfig.from_dict(config_data)
            
            # Register server
            await self.mcp_registry.register_server(config)
            
            return VextirEvent(
                event_type="mcp.server.registered",
                event_category="OUTPUT",
                data={
                    "server_id": config.id,
                    "server_name": config.name
                }
            )
            
        except Exception as e:
            logger.error(f"Error registering MCP server: {e}")
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={"error": str(e)}
            )
    
    async def _handle_server_list(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle server list request."""
        agent_id = event.agent_id
        
        if agent_id:
            # Get servers for specific agent
            servers = self.mcp_registry.get_servers_for_agent(agent_id)
        else:
            # Get all servers
            servers = self.mcp_registry.list_servers()
        
        server_list = []
        for server in servers:
            server_info = {
                "id": server.id,
                "name": server.name,
                "connection_type": server.connection_type.value,
                "connected": self.mcp_registry.is_connected(server.id),
                "access_scopes": server.access_scopes,
                "auto_start": server.auto_start,
            }
            
            # Add tool count if connected
            if server_info["connected"]:
                client = self.mcp_registry.get_client(server.id)
                try:
                    tools = await client.list_tools()
                    server_info["tool_count"] = len(tools)
                except:
                    server_info["tool_count"] = 0
            
            server_list.append(server_info)
        
        return VextirEvent(
            event_type="mcp.server.list_result",
            event_category="OUTPUT",
            data={
                "servers": server_list,
                "total": len(server_list)
            }
        )
    
    async def _handle_server_status(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle server status request."""
        server_id = event.data.get("server_id")
        if not server_id:
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={"error": "Missing server_id"}
            )
        
        try:
            status = await self.mcp_registry.get_server_status(server_id)
            
            return VextirEvent(
                event_type="mcp.server.status_result",
                event_category="OUTPUT",
                data=status
            )
            
        except Exception as e:
            logger.error(f"Error getting server status: {e}")
            return VextirEvent(
                event_type="mcp.server.error",
                event_category="OUTPUT",
                data={
                    "server_id": server_id,
                    "error": str(e)
                }
            )
    
    async def _handle_tool_list(self, event: VextirEvent) -> Optional[VextirEvent]:
        """Handle tool list request."""
        server_id = event.data.get("server_id")
        agent_id = event.agent_id
        
        tools_by_server = {}
        
        if server_id:
            # Get tools for specific server
            if not self.mcp_registry.is_connected(server_id):
                return VextirEvent(
                    event_type="mcp.tool.error",
                    event_category="OUTPUT",
                    data={"error": f"Server {server_id} not connected"}
                )
            
            client = self.mcp_registry.get_client(server_id)
            tools = await client.list_tools()
            tools_by_server[server_id] = tools
        else:
            # Get tools from all connected servers accessible to agent
            if agent_id:
                servers = self.mcp_registry.get_servers_for_agent(agent_id)
            else:
                servers = self.mcp_registry.list_servers()
            
            for server in servers:
                if self.mcp_registry.is_connected(server.id):
                    client = self.mcp_registry.get_client(server.id)
                    try:
                        tools = await client.list_tools()
                        tools_by_server[server.id] = tools
                    except Exception as e:
                        logger.error(f"Error listing tools for server {server.id}: {e}")
        
        # Format response
        all_tools = []
        for server_id, tools in tools_by_server.items():
            for tool in tools:
                all_tools.append({
                    "server_id": server_id,
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                })
        
        return VextirEvent(
            event_type="mcp.tool.list_result",
            event_category="OUTPUT",
            data={
                "tools": all_tools,
                "total": len(all_tools),
                "servers": list(tools_by_server.keys())
            }
        )
    
    async def _auto_connect_server(self, server: MCPServerConfig) -> None:
        """Auto-connect to a server with retry logic."""
        retry_count = 0
        max_retries = 3
        retry_delay = 5
        
        while retry_count < max_retries:
            try:
                await self._handle_server_connect(
                    VextirEvent(
                        event_type="mcp.server.connect",
                        event_category="INTERNAL",
                        data={"server_id": server.id}
                    )
                )
                logger.info(f"Auto-connected to MCP server: {server.id}")
                break
                
            except Exception as e:
                retry_count += 1
                logger.error(
                    f"Failed to auto-connect to server {server.id} "
                    f"(attempt {retry_count}/{max_retries}): {e}"
                )
                
                if retry_count < max_retries:
                    await asyncio.sleep(retry_delay * retry_count)
                else:
                    logger.error(f"Giving up on auto-connecting to server {server.id}")
    
    def get_capabilities(self) -> List[str]:
        """Get driver capabilities."""
        return [
            "mcp.server.management",
            "mcp.tool.execution",
            "mcp.security.validation",
            "mcp.sandbox.isolation",
        ]