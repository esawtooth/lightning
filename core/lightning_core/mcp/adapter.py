"""Adapter to expose MCP server tools to the Lightning tool registry."""

import json
from typing import Any, Dict, List, Optional
import logging

from ..tools.models import Tool, ToolType, ToolScope, ToolCategory
from .client import MCPClient, MCPTool
from .registry import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolAdapter:
    """Adapter that exposes MCP server tools to the Lightning tool registry."""
    
    def __init__(self, mcp_client: MCPClient, server_config: MCPServerConfig):
        self.mcp_client = mcp_client
        self.server_config = server_config
        self._tool_cache: Optional[List[Tool]] = None
    
    async def discover_tools(self) -> List[Tool]:
        """Discover tools from MCP server and convert to Lightning format."""
        try:
            mcp_tools = await self.mcp_client.list_tools()
            
            lightning_tools = []
            for mcp_tool in mcp_tools:
                tool = self._convert_to_lightning_tool(mcp_tool)
                lightning_tools.append(tool)
            
            self._tool_cache = lightning_tools
            logger.info(
                f"Discovered {len(lightning_tools)} tools from MCP server {self.server_config.id}"
            )
            
            return lightning_tools
            
        except Exception as e:
            logger.error(f"Error discovering tools from MCP server: {e}")
            return []
    
    def _convert_to_lightning_tool(self, mcp_tool: MCPTool) -> Tool:
        """Convert an MCP tool to Lightning tool format."""
        # Generate unique tool ID
        tool_id = f"mcp_{self.server_config.id}_{mcp_tool.name}"
        
        # Map access scopes
        scopes = []
        for scope_str in self.server_config.access_scopes:
            try:
                scopes.append(ToolScope[scope_str])
            except KeyError:
                logger.warning(f"Unknown scope: {scope_str}")
        
        # Determine category based on tool name/description
        category = self._infer_category(mcp_tool)
        
        # Create Lightning tool
        return Tool(
            id=tool_id,
            name=mcp_tool.name,
            description=mcp_tool.description,
            type=ToolType.MCP_SERVER,
            category=category,
            provider=f"mcp:{self.server_config.id}",
            input_schema=mcp_tool.input_schema,
            output_schema=mcp_tool.output_schema or {"type": "object"},
            scopes=scopes,
            metadata={
                "server_id": self.server_config.id,
                "server_name": self.server_config.name,
                "original_name": mcp_tool.name,
                "connection_type": self.server_config.connection_type.value,
            },
            cost_config={
                "model": "mcp_execution",
                "estimated_tokens": 100,  # Default estimate
                "rate_per_1k_tokens": 0.0,  # MCP tools are free to execute
            },
            rate_limit={
                "max_calls_per_minute": 60,
                "max_calls_per_hour": 1000,
            }
        )
    
    def _infer_category(self, mcp_tool: MCPTool) -> ToolCategory:
        """Infer tool category based on name and description."""
        name_lower = mcp_tool.name.lower()
        desc_lower = mcp_tool.description.lower()
        
        # File system operations
        if any(word in name_lower for word in ["file", "directory", "path", "fs"]):
            return ToolCategory.PRODUCTIVITY
        
        # Code/development tools
        if any(word in name_lower for word in ["code", "git", "compile", "build", "test"]):
            return ToolCategory.PRODUCTIVITY
        
        # Search/information tools
        if any(word in name_lower for word in ["search", "find", "query", "lookup"]):
            return ToolCategory.SEARCH
        
        # Communication tools
        if any(word in name_lower for word in ["email", "message", "notify", "send"]):
            return ToolCategory.COMMUNICATION
        
        # API/web tools
        if any(word in name_lower for word in ["api", "http", "request", "fetch"]):
            return ToolCategory.SEARCH
        
        # Database tools
        if any(word in name_lower for word in ["database", "sql", "query", "db"]):
            return ToolCategory.PRODUCTIVITY
        
        # Default to utility
        return ToolCategory.UTILITY
    
    async def execute_tool(self, 
                          tool_id: str, 
                          parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool through the MCP server."""
        # Extract original tool name from ID
        if not tool_id.startswith(f"mcp_{self.server_config.id}_"):
            raise ValueError(f"Invalid tool ID for this adapter: {tool_id}")
        
        original_name = tool_id[len(f"mcp_{self.server_config.id}_"):]
        
        try:
            # Execute through MCP client
            result = await self.mcp_client.execute_tool(original_name, parameters)
            
            # Wrap result in standard format
            return {
                "success": True,
                "result": result,
                "server_id": self.server_config.id,
                "tool_name": original_name,
            }
            
        except Exception as e:
            logger.error(f"Error executing MCP tool {original_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": self.server_config.id,
                "tool_name": original_name,
            }
    
    def get_tool_by_id(self, tool_id: str) -> Optional[Tool]:
        """Get a specific tool by ID."""
        if not self._tool_cache:
            return None
        
        for tool in self._tool_cache:
            if tool.id == tool_id:
                return tool
        
        return None
    
    def get_tool_by_name(self, name: str) -> Optional[Tool]:
        """Get a specific tool by its original name."""
        if not self._tool_cache:
            return None
        
        for tool in self._tool_cache:
            if tool.metadata.get("original_name") == name:
                return tool
        
        return None
    
    async def refresh_tools(self) -> List[Tool]:
        """Refresh the tool list from the MCP server."""
        self._tool_cache = None
        return await self.discover_tools()


class MCPToolRegistry:
    """Registry for managing tools from multiple MCP servers."""
    
    def __init__(self):
        self.adapters: Dict[str, MCPToolAdapter] = {}
        self._tool_index: Dict[str, str] = {}  # tool_id -> server_id mapping
    
    async def register_adapter(self, 
                             server_id: str,
                             mcp_client: MCPClient,
                             server_config: MCPServerConfig) -> None:
        """Register an MCP tool adapter."""
        adapter = MCPToolAdapter(mcp_client, server_config)
        self.adapters[server_id] = adapter
        
        # Discover and index tools
        tools = await adapter.discover_tools()
        for tool in tools:
            self._tool_index[tool.id] = server_id
        
        logger.info(f"Registered MCP adapter for server {server_id} with {len(tools)} tools")
    
    def unregister_adapter(self, server_id: str) -> None:
        """Unregister an MCP tool adapter."""
        if server_id in self.adapters:
            # Remove from tool index
            self._tool_index = {
                tid: sid for tid, sid in self._tool_index.items() 
                if sid != server_id
            }
            
            del self.adapters[server_id]
            logger.info(f"Unregistered MCP adapter for server {server_id}")
    
    async def get_all_tools(self) -> List[Tool]:
        """Get all tools from all registered MCP servers."""
        all_tools = []
        for adapter in self.adapters.values():
            tools = await adapter.discover_tools()
            all_tools.extend(tools)
        return all_tools
    
    async def get_tools_for_server(self, server_id: str) -> List[Tool]:
        """Get tools for a specific MCP server."""
        adapter = self.adapters.get(server_id)
        if not adapter:
            return []
        return await adapter.discover_tools()
    
    async def execute_tool(self, 
                          tool_id: str,
                          parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by ID."""
        server_id = self._tool_index.get(tool_id)
        if not server_id:
            raise ValueError(f"Tool {tool_id} not found in any MCP server")
        
        adapter = self.adapters.get(server_id)
        if not adapter:
            raise ValueError(f"MCP server {server_id} not registered")
        
        return await adapter.execute_tool(tool_id, parameters)
    
    def get_tool_by_id(self, tool_id: str) -> Optional[Tool]:
        """Get a specific tool by ID."""
        server_id = self._tool_index.get(tool_id)
        if not server_id:
            return None
        
        adapter = self.adapters.get(server_id)
        if not adapter:
            return None
        
        return adapter.get_tool_by_id(tool_id)
    
    async def refresh_all_tools(self) -> None:
        """Refresh tools from all MCP servers."""
        self._tool_index.clear()
        
        for server_id, adapter in self.adapters.items():
            tools = await adapter.refresh_tools()
            for tool in tools:
                self._tool_index[tool.id] = server_id