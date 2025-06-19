"""Enhanced Agent Driver with MCP support."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Set
import logging

from .drivers import AgentDriver, DriverManifest
from .events import Event
from ..mcp import MCPRegistry, MCPToolAdapter, MCPToolRegistry
from ..tools.registry import ToolRegistry
from ..tools.models import Tool, ToolType

logger = logging.getLogger(__name__)


class EnhancedAgentDriver(AgentDriver):
    """Enhanced agent driver with dynamic MCP tool support."""
    
    def __init__(self,
                 manifest: DriverManifest,
                 config: Optional[Dict[str, Any]] = None,
                 mcp_registry: Optional[MCPRegistry] = None,
                 tool_registry: Optional[ToolRegistry] = None):
        super().__init__(manifest, config)
        self.mcp_registry = mcp_registry
        self.tool_registry = tool_registry
        self.mcp_tool_registry = MCPToolRegistry()
        self.agent_id = manifest.id
        self._available_tools_cache: Optional[List[Dict]] = None
        self._cache_timestamp: Optional[float] = None
        self.cache_ttl = 60.0  # Cache tools for 60 seconds
        
        # Track MCP servers we're connected to
        self._connected_mcp_servers: Set[str] = set()
        
    async def initialize(self) -> None:
        """Initialize the agent driver and connect to MCP servers."""
        await super().initialize()
        
        if self.mcp_registry:
            # Discover available MCP servers for this agent
            mcp_servers = self.mcp_registry.get_servers_for_agent(self.agent_id)
            
            # Connect to auto-start servers
            for server in mcp_servers:
                if server.auto_start:
                    try:
                        await self._connect_mcp_server(server.id)
                    except Exception as e:
                        logger.error(f"Failed to connect to MCP server {server.id}: {e}")
    
    async def _connect_mcp_server(self, server_id: str) -> None:
        """Connect to an MCP server and register its tools."""
        if not self.mcp_registry:
            return
            
        # Connect if not already connected
        if not self.mcp_registry.is_connected(server_id):
            await self.mcp_registry.connect_server(server_id)
        
        # Get server config and client
        server = await self.mcp_registry.get_server(server_id)
        client = self.mcp_registry.get_client(server_id)
        
        if server and client:
            # Register adapter for this server
            await self.mcp_tool_registry.register_adapter(server_id, client, server)
            self._connected_mcp_servers.add(server_id)
            
            # Invalidate cache
            self._available_tools_cache = None
            
            logger.info(f"Connected to MCP server {server_id} for agent {self.agent_id}")
    
    async def _disconnect_mcp_server(self, server_id: str) -> None:
        """Disconnect from an MCP server and unregister its tools."""
        if server_id in self._connected_mcp_servers:
            self.mcp_tool_registry.unregister_adapter(server_id)
            self._connected_mcp_servers.remove(server_id)
            
            # Invalidate cache
            self._available_tools_cache = None
            
            logger.info(f"Disconnected from MCP server {server_id} for agent {self.agent_id}")
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get all available tools including static and MCP tools."""
        # Check cache
        import time
        current_time = time.time()
        if (self._available_tools_cache is not None and 
            self._cache_timestamp is not None and
            current_time - self._cache_timestamp < self.cache_ttl):
            return self._available_tools_cache
        
        tools = []
        
        # Get static tools from registry
        if self.tool_registry:
            static_tools = await self.tool_registry.get_tools_for_agent(self.agent_id)
            for tool in static_tools:
                tools.append(self._tool_to_dict(tool))
        
        # Get tools from hardcoded config
        for tool_config in self.tools:
            if isinstance(tool_config, dict):
                tools.append(tool_config)
        
        # Get dynamic MCP tools
        mcp_tools = await self.mcp_tool_registry.get_all_tools()
        for tool in mcp_tools:
            tools.append(self._tool_to_dict(tool))
        
        # Update cache
        self._available_tools_cache = tools
        self._cache_timestamp = current_time
        
        return tools
    
    def _tool_to_dict(self, tool: Tool) -> Dict[str, Any]:
        """Convert a Tool object to dictionary format for LLM."""
        return {
            "name": tool.id,  # Use ID as the function name
            "description": tool.description,
            "parameters": tool.input_schema,
            "metadata": {
                "type": tool.type.value,
                "provider": tool.provider,
                "category": tool.category.value if tool.category else "utility",
                "original_name": tool.metadata.get("original_name", tool.name)
            }
        }
    
    async def execute_tool(self, tool_id: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool by ID, supporting both static and MCP tools."""
        # Check if it's an MCP tool
        if tool_id.startswith("mcp_"):
            return await self.mcp_tool_registry.execute_tool(tool_id, parameters)
        
        # Otherwise, execute through normal tool registry
        if self.tool_registry:
            return await self.tool_registry.execute_tool(tool_id, parameters)
        
        raise ValueError(f"Tool {tool_id} not found")
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle events with MCP server management support."""
        result_events = []
        
        # Handle MCP server management events
        if event.type == "agent.mcp.connect":
            server_id = event.metadata.get("server_id")
            if server_id:
                await self._connect_mcp_server(server_id)
                result_events.append(Event(
                    type="agent.mcp.connected",
                    metadata={
                        "agent_id": self.agent_id,
                        "server_id": server_id,
                        "tool_count": len(await self.mcp_tool_registry.get_tools_for_server(server_id))
                    }
                ))
        
        elif event.type == "agent.mcp.disconnect":
            server_id = event.metadata.get("server_id")
            if server_id:
                await self._disconnect_mcp_server(server_id)
                result_events.append(Event(
                    type="agent.mcp.disconnected",
                    metadata={
                        "agent_id": self.agent_id,
                        "server_id": server_id
                    }
                ))
        
        elif event.type == "agent.mcp.list_servers":
            if self.mcp_registry:
                servers = self.mcp_registry.get_servers_for_agent(self.agent_id)
                server_list = []
                for server in servers:
                    server_info = {
                        "id": server.id,
                        "name": server.name,
                        "connected": server.id in self._connected_mcp_servers,
                        "connection_type": server.connection_type.value,
                        "access_scopes": server.access_scopes
                    }
                    if server_info["connected"]:
                        tools = await self.mcp_tool_registry.get_tools_for_server(server.id)
                        server_info["tool_count"] = len(tools)
                    server_list.append(server_info)
                
                result_events.append(Event(
                    type="agent.mcp.server_list",
                    metadata={
                        "agent_id": self.agent_id,
                        "servers": server_list
                    }
                ))
        
        elif event.type == "agent.mcp.refresh_tools":
            # Refresh all MCP tools
            await self.mcp_tool_registry.refresh_all_tools()
            self._available_tools_cache = None
            
            tools = await self.get_available_tools()
            result_events.append(Event(
                type="agent.mcp.tools_refreshed",
                metadata={
                    "agent_id": self.agent_id,
                    "tool_count": len(tools)
                }
            ))
        
        else:
            # Let subclass handle other events
            subclass_events = await super().handle_event(event)
            result_events.extend(subclass_events)
        
        return result_events
    
    async def shutdown(self) -> None:
        """Cleanup agent resources and disconnect from MCP servers."""
        # Disconnect from all MCP servers
        for server_id in list(self._connected_mcp_servers):
            try:
                await self._disconnect_mcp_server(server_id)
            except Exception as e:
                logger.error(f"Error disconnecting from MCP server {server_id}: {e}")
        
        await super().shutdown()
    
    def get_capabilities(self) -> List[str]:
        """Get driver capabilities including MCP management."""
        base_capabilities = super().get_capabilities()
        mcp_capabilities = [
            "agent.mcp.connect",
            "agent.mcp.disconnect",
            "agent.mcp.list_servers",
            "agent.mcp.refresh_tools",
        ]
        return base_capabilities + mcp_capabilities


class MCPAwareAgentFactory:
    """Factory for creating MCP-aware agents."""
    
    @staticmethod
    def create_agent(
        manifest: DriverManifest,
        config: Optional[Dict[str, Any]] = None,
        mcp_registry: Optional[MCPRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        base_class: type = EnhancedAgentDriver
    ) -> EnhancedAgentDriver:
        """Create an MCP-aware agent instance."""
        
        # Create custom agent class that inherits from both base_class and EnhancedAgentDriver
        if base_class != EnhancedAgentDriver:
            class MCPAwareAgent(base_class, EnhancedAgentDriver):
                """Custom agent with MCP support."""
                
                def __init__(self, manifest, config=None):
                    # Initialize both parent classes
                    base_class.__init__(self, manifest, config)
                    EnhancedAgentDriver.__init__(
                        self, manifest, config, mcp_registry, tool_registry
                    )
                
                async def get_available_tools(self) -> List[Dict[str, Any]]:
                    """Merge tools from both parent classes."""
                    # Get MCP tools
                    mcp_tools = await EnhancedAgentDriver.get_available_tools(self)
                    
                    # Get base class tools if it has the method
                    if hasattr(base_class, 'get_available_tools'):
                        base_tools = await base_class.get_available_tools(self)
                        # Merge, avoiding duplicates
                        tool_names = {t['name'] for t in mcp_tools}
                        for tool in base_tools:
                            if tool['name'] not in tool_names:
                                mcp_tools.append(tool)
                    
                    return mcp_tools
            
            return MCPAwareAgent(manifest, config)
        else:
            # Just use EnhancedAgentDriver directly
            return EnhancedAgentDriver(manifest, config, mcp_registry, tool_registry)