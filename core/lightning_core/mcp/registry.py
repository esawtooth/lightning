"""MCP server registry with persistence and validation."""

import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
import logging

from ..abstractions.storage import StorageProvider
from .client import MCPConnectionType, create_mcp_client
from .sandbox import SandboxConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    id: str
    name: str
    connection_type: MCPConnectionType
    endpoint: str  # URL for SSE/WebSocket, command for stdio
    capabilities: List[str]
    sandbox_config: SandboxConfig
    access_scopes: List[str]  # Which agents can use this server
    auto_start: bool = False
    restart_policy: Literal["never", "on-failure", "always"] = "never"
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data["connection_type"] = self.connection_type.value
        data["sandbox_config"] = self.sandbox_config.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        """Create from dictionary."""
        data = data.copy()
        data["connection_type"] = MCPConnectionType(data["connection_type"])
        data["sandbox_config"] = SandboxConfig.from_dict(data["sandbox_config"])
        return cls(**data)


class MCPRegistry:
    """Registry for MCP servers with persistence."""
    
    STORAGE_COLLECTION = "mcp_servers"
    
    def __init__(self, storage: StorageProvider):
        self.storage = storage
        self._servers: Dict[str, MCPServerConfig] = {}
        self._connections: Dict[str, Any] = {}  # server_id -> MCPClient
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """Initialize registry and load servers from storage."""
        await self._load_from_storage()
        
        # Auto-start servers if configured
        for server in self._servers.values():
            if server.auto_start:
                try:
                    await self.connect_server(server.id)
                except Exception as e:
                    logger.error(f"Failed to auto-start server {server.id}: {e}")
    
    async def _load_from_storage(self) -> None:
        """Load server configurations from storage."""
        try:
            servers = await self.storage.list_documents(self.STORAGE_COLLECTION)
            for server_data in servers:
                server = MCPServerConfig.from_dict(server_data)
                self._servers[server.id] = server
            logger.info(f"Loaded {len(self._servers)} MCP servers from storage")
        except Exception as e:
            logger.warning(f"Failed to load MCP servers from storage: {e}")
    
    async def _persist_to_storage(self) -> None:
        """Persist server configurations to storage."""
        for server in self._servers.values():
            await self.storage.upsert_document(
                self.STORAGE_COLLECTION,
                server.id,
                server.to_dict()
            )
    
    async def register_server(self, config: MCPServerConfig) -> None:
        """Register a new MCP server with validation."""
        async with self._lock:
            # Validate server ID uniqueness
            if config.id in self._servers:
                raise ValueError(f"Server with ID '{config.id}' already exists")
            
            # Validate endpoint
            await self._validate_server_config(config)
            
            # Store in registry
            self._servers[config.id] = config
            
            # Persist to storage
            await self._persist_to_storage()
            
            logger.info(f"Registered MCP server: {config.id}")
    
    async def unregister_server(self, server_id: str) -> None:
        """Unregister an MCP server."""
        async with self._lock:
            if server_id not in self._servers:
                raise ValueError(f"Server '{server_id}' not found")
            
            # Disconnect if connected
            if server_id in self._connections:
                await self.disconnect_server(server_id)
            
            # Remove from registry
            del self._servers[server_id]
            
            # Remove from storage
            await self.storage.delete_document(self.STORAGE_COLLECTION, server_id)
            
            logger.info(f"Unregistered MCP server: {server_id}")
    
    async def update_server(self, server_id: str, config: MCPServerConfig) -> None:
        """Update an existing MCP server configuration."""
        async with self._lock:
            if server_id not in self._servers:
                raise ValueError(f"Server '{server_id}' not found")
            
            # Validate new configuration
            await self._validate_server_config(config)
            
            # Disconnect if connected and config changed
            if server_id in self._connections:
                old_config = self._servers[server_id]
                if (old_config.endpoint != config.endpoint or 
                    old_config.connection_type != config.connection_type):
                    await self.disconnect_server(server_id)
            
            # Update configuration
            self._servers[server_id] = config
            
            # Persist to storage
            await self._persist_to_storage()
            
            logger.info(f"Updated MCP server: {server_id}")
    
    async def get_server(self, server_id: str) -> Optional[MCPServerConfig]:
        """Get a specific server configuration."""
        return self._servers.get(server_id)
    
    def list_servers(self) -> List[MCPServerConfig]:
        """List all registered servers."""
        return list(self._servers.values())
    
    def get_servers_for_agent(self, agent_id: str) -> List[MCPServerConfig]:
        """Get MCP servers accessible to a specific agent."""
        agent_scope = self._get_agent_scope(agent_id)
        return [
            server for server in self._servers.values()
            if agent_scope in server.access_scopes or "AGENT_ALL" in server.access_scopes
        ]
    
    def get_servers_for_scope(self, scope: str) -> List[MCPServerConfig]:
        """Get MCP servers for a specific access scope."""
        return [
            server for server in self._servers.values()
            if scope in server.access_scopes
        ]
    
    async def connect_server(self, server_id: str) -> None:
        """Connect to an MCP server."""
        if server_id in self._connections:
            logger.warning(f"Server {server_id} already connected")
            return
        
        server = self._servers.get(server_id)
        if not server:
            raise ValueError(f"Server '{server_id}' not found")
        
        # Create client
        client = create_mcp_client(
            server.id,
            server.connection_type,
            server.endpoint
        )
        
        # Connect
        try:
            await client.connect()
            self._connections[server_id] = client
            logger.info(f"Connected to MCP server: {server_id}")
        except Exception as e:
            logger.error(f"Failed to connect to server {server_id}: {e}")
            raise
    
    async def disconnect_server(self, server_id: str) -> None:
        """Disconnect from an MCP server."""
        if server_id not in self._connections:
            return
        
        client = self._connections[server_id]
        try:
            await client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting from server {server_id}: {e}")
        finally:
            del self._connections[server_id]
            logger.info(f"Disconnected from MCP server: {server_id}")
    
    def is_connected(self, server_id: str) -> bool:
        """Check if a server is connected."""
        return server_id in self._connections
    
    def get_client(self, server_id: str) -> Optional[Any]:
        """Get the MCP client for a connected server."""
        return self._connections.get(server_id)
    
    async def _validate_server_config(self, config: MCPServerConfig) -> None:
        """Validate server configuration."""
        if config.connection_type == MCPConnectionType.SSE:
            await self._validate_sse_endpoint(config.endpoint)
        elif config.connection_type == MCPConnectionType.STDIO:
            await self._validate_stdio_command(config.endpoint)
        
        # Validate access scopes
        valid_scopes = ["AGENT_CONSEIL", "AGENT_VEX", "AGENT_ALL", "SYSTEM", "USER"]
        for scope in config.access_scopes:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid access scope: {scope}")
    
    async def _validate_sse_endpoint(self, endpoint: str) -> None:
        """Validate SSE endpoint is reachable."""
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("SSE endpoint must be a valid HTTP(S) URL")
        
        # Could add actual connectivity check here
        logger.debug(f"Validated SSE endpoint: {endpoint}")
    
    async def _validate_stdio_command(self, command: str) -> None:
        """Validate stdio command can be executed."""
        import shutil
        
        # Check if command exists
        cmd_parts = command.split()
        if not cmd_parts:
            raise ValueError("Empty stdio command")
        
        executable = cmd_parts[0]
        
        # Check if it's a full path or needs to be found in PATH
        if "/" not in executable:
            if not shutil.which(executable):
                raise ValueError(f"Command '{executable}' not found in PATH")
        
        logger.debug(f"Validated stdio command: {command}")
    
    def _get_agent_scope(self, agent_id: str) -> str:
        """Get the access scope for an agent ID."""
        # Map agent IDs to scopes
        if "conseil" in agent_id.lower():
            return "AGENT_CONSEIL"
        elif "vex" in agent_id.lower():
            return "AGENT_VEX"
        else:
            return "AGENT_ALL"
    
    async def get_server_status(self, server_id: str) -> Dict[str, Any]:
        """Get status information for a server."""
        server = self._servers.get(server_id)
        if not server:
            raise ValueError(f"Server '{server_id}' not found")
        
        status = {
            "id": server.id,
            "name": server.name,
            "connected": self.is_connected(server_id),
            "connection_type": server.connection_type.value,
            "endpoint": server.endpoint,
            "access_scopes": server.access_scopes,
            "auto_start": server.auto_start,
        }
        
        # If connected, get additional info
        if status["connected"]:
            client = self.get_client(server_id)
            try:
                tools = await client.list_tools()
                status["tool_count"] = len(tools)
                status["tools"] = [t.name for t in tools]
                status["capabilities"] = [
                    {"name": cap.name, "version": cap.version}
                    for cap in await client.get_capabilities()
                ]
            except Exception as e:
                status["error"] = str(e)
        
        return status