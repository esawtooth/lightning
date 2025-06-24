"""
Unified tool registry that replaces all existing registries.

This is a complete redesign focused on simplicity, performance, and maintainability.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypeVar, Callable
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Type variable for tool implementations
T = TypeVar('T')

class ToolType(Enum):
    """Types of tools in the system."""
    AGENT = "agent"
    LLM = "llm"
    NATIVE = "native"
    MCP = "mcp"
    API = "api"

class AccessScope(Enum):
    """Access scopes for tools."""
    PLANNER = "planner"
    AGENT_CONSEIL = "agent_conseil"
    AGENT_VEX = "agent_vex"
    AGENT_ALL = "agent_all"
    SYSTEM = "system"
    USER = "user"

@dataclass(frozen=True)
class ToolMetadata:
    """Immutable tool metadata."""
    id: str
    name: str
    description: str
    tool_type: ToolType
    access_scopes: Set[AccessScope] = field(default_factory=set)
    capabilities: Set[str] = field(default_factory=set)
    version: str = "1.0.0"
    enabled: bool = True
    
    # Planner-specific (only used by planner)
    inputs: Optional[Dict[str, str]] = None
    produces: Optional[List[str]] = None
    
    # Runtime configuration (lazy-loaded)
    config: Optional[Dict[str, Any]] = None
    
    def is_accessible_to(self, scope: AccessScope, user_id: Optional[str] = None) -> bool:
        """Check if tool is accessible in given scope."""
        return scope in self.access_scopes
    
    def has_capability(self, capability: str) -> bool:
        """Check if tool has specific capability."""
        return capability in self.capabilities

class ToolProvider(ABC):
    """Abstract interface for tool providers."""
    
    @abstractmethod
    async def get_tool_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        pass
    
    @abstractmethod
    async def list_tool_metadata(self) -> List[ToolMetadata]:
        """List all available tool metadata."""
        pass
    
    @abstractmethod
    async def execute_tool(self, tool_id: str, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute a tool (lazy-loaded)."""
        pass
    
    @abstractmethod
    async def is_available(self, tool_id: str) -> bool:
        """Check if tool is currently available."""
        pass

class DefaultToolProvider(ToolProvider):
    """Default provider for built-in Lightning tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._load_builtin_tools()
    
    def _load_builtin_tools(self):
        """Load built-in tool definitions."""
        
        # Agent tools
        self._tools["agent.conseil"] = ToolMetadata(
            id="agent.conseil",
            name="Conseil Agent",
            description="Research and bash execution agent with context access",
            tool_type=ToolType.AGENT,
            access_scopes={AccessScope.PLANNER},
            capabilities={"task_execution", "bash_access", "research", "context_access"},
            inputs={"objective": "string", "additional_context": "string"},
            produces=["event.agent.conseil.start"],
        )
        
        self._tools["agent.vex"] = ToolMetadata(
            id="agent.vex",
            name="Vex Agent", 
            description="Voice interaction agent for phone calls",
            tool_type=ToolType.AGENT,
            access_scopes={AccessScope.PLANNER},
            capabilities={"voice_interaction", "phone_calls", "context_access"},
            inputs={"objective": "string", "phone_number": "string", "additional_context": "string"},
            produces=["event.agent.vex.start"],
        )
        
        # LLM tools
        self._tools["llm.summarize"] = ToolMetadata(
            id="llm.summarize",
            name="LLM Summarize",
            description="Summarize text using GPT-4 Turbo",
            tool_type=ToolType.LLM,
            access_scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL},
            capabilities={"text_generation", "summarization"},
            inputs={"text": "string", "style": "string"},
            produces=["event.summary_ready"],
        )
        
        self._tools["llm.general_prompt"] = ToolMetadata(
            id="llm.general_prompt",
            name="LLM General",
            description="General LLM prompt processing",
            tool_type=ToolType.LLM,
            access_scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL},
            capabilities={"text_generation", "reasoning", "multi_model"},
            inputs={"system_prompt": "string", "user_prompt": "string", "model": "string"},
            produces=["event.llm_response"],
        )
        
        # Native tools
        self._tools["email.send"] = ToolMetadata(
            id="email.send",
            name="Email Send",
            description="Send email with attachments",
            tool_type=ToolType.NATIVE,
            access_scopes={AccessScope.AGENT_ALL},
            capabilities={"email_send", "communication"},
            inputs={"to": "string", "subject": "string", "body": "string", "attachments": "string"},
            produces=["event.email.sent"],
        )
        
        self._tools["chat.sendTeamsMessage"] = ToolMetadata(
            id="chat.sendTeamsMessage",
            name="Teams Message",
            description="Send Microsoft Teams message",
            tool_type=ToolType.NATIVE,
            access_scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL},
            capabilities={"team_communication", "messaging"},
            inputs={"channel_id": "string", "content": "string"},
            produces=["event.teams_message_sent"],
        )
        
        # Scheduling tools
        self._tools["cron.configure"] = ToolMetadata(
            id="cron.configure",
            name="Cron Configure",
            description="Configure scheduled plan execution",
            tool_type=ToolType.NATIVE,
            access_scopes={AccessScope.PLANNER},
            capabilities={"scheduling", "automation", "cron_management"},
            inputs={"plan_id": "string", "cron_expression": "string", "description": "string"},
            produces=["event.cron.configured"],
        )
        
        self._tools["event.schedule.create"] = ToolMetadata(
            id="event.schedule.create",
            name="Event Schedule",
            description="Create scheduled events",
            tool_type=ToolType.NATIVE,
            access_scopes={AccessScope.PLANNER},
            capabilities={"scheduling", "event_management"},
            inputs={"title": "string", "cron": "string", "start_time": "datetime", "end_time": "datetime"},
            produces=["event.scheduled_event"],
        )
        
        self._tools["event.timer.start"] = ToolMetadata(
            id="event.timer.start",
            name="Event Timer",
            description="Create timed events",
            tool_type=ToolType.NATIVE,
            access_scopes={AccessScope.PLANNER},
            capabilities={"timing", "event_management"},
            inputs={"duration": "integer"},
            produces=["event.timed_event"],
        )
        
        logger.info(f"Loaded {len(self._tools)} built-in tools")
    
    async def get_tool_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        return self._tools.get(tool_id)
    
    async def list_tool_metadata(self) -> List[ToolMetadata]:
        return [tool for tool in self._tools.values() if tool.enabled]
    
    async def execute_tool(self, tool_id: str, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        # This would delegate to actual tool implementations
        # For now, just log the execution
        logger.info(f"Executing tool {tool_id} with inputs: {inputs}")
        return {"status": "executed", "tool_id": tool_id, "inputs": inputs}
    
    async def is_available(self, tool_id: str) -> bool:
        tool = self._tools.get(tool_id)
        return tool is not None and tool.enabled

class MCPToolProvider(ToolProvider):
    """Provider for MCP server tools."""
    
    def __init__(self, mcp_registry):
        self.mcp_registry = mcp_registry
        self._tool_cache: Dict[str, ToolMetadata] = {}
        self._cache_valid = False
    
    async def _refresh_cache(self):
        """Refresh tool cache from MCP servers."""
        if self._cache_valid:
            return
            
        self._tool_cache.clear()
        
        # Get tools from connected MCP servers
        for server in self.mcp_registry.list_servers():
            if self.mcp_registry.is_connected(server.id):
                try:
                    client = self.mcp_registry.get_client(server.id)
                    mcp_tools = await client.list_tools()
                    
                    for mcp_tool in mcp_tools:
                        tool_id = f"mcp.{server.id}.{mcp_tool.name}"
                        
                        # Convert access scopes
                        access_scopes = set()
                        for scope in server.access_scopes:
                            if scope == "AGENT_CONSEIL":
                                access_scopes.add(AccessScope.AGENT_CONSEIL)
                            elif scope == "AGENT_VEX":
                                access_scopes.add(AccessScope.AGENT_VEX)
                            elif scope == "AGENT_ALL":
                                access_scopes.add(AccessScope.AGENT_ALL)
                            elif scope == "SYSTEM":
                                access_scopes.add(AccessScope.SYSTEM)
                            elif scope == "USER":
                                access_scopes.add(AccessScope.USER)
                        
                        self._tool_cache[tool_id] = ToolMetadata(
                            id=tool_id,
                            name=mcp_tool.name,
                            description=mcp_tool.description or f"MCP tool from {server.name}",
                            tool_type=ToolType.MCP,
                            access_scopes=access_scopes,
                            capabilities=set(server.capabilities),
                            config={"server_id": server.id, "mcp_name": mcp_tool.name}
                        )
                        
                except Exception as e:
                    logger.warning(f"Failed to get tools from MCP server {server.id}: {e}")
        
        self._cache_valid = True
        logger.info(f"Cached {len(self._tool_cache)} MCP tools")
    
    async def get_tool_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        await self._refresh_cache()
        return self._tool_cache.get(tool_id)
    
    async def list_tool_metadata(self) -> List[ToolMetadata]:
        await self._refresh_cache()
        return list(self._tool_cache.values())
    
    async def execute_tool(self, tool_id: str, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        tool = await self.get_tool_metadata(tool_id)
        if not tool or not tool.config:
            raise ValueError(f"Tool {tool_id} not found or not configured")
        
        server_id = tool.config["server_id"]
        mcp_name = tool.config["mcp_name"]
        
        client = self.mcp_registry.get_client(server_id)
        if not client:
            raise RuntimeError(f"MCP server {server_id} not connected")
        
        return await client.call_tool(mcp_name, inputs)
    
    async def is_available(self, tool_id: str) -> bool:
        tool = await self.get_tool_metadata(tool_id)
        if not tool or not tool.config:
            return False
        
        server_id = tool.config["server_id"]
        return self.mcp_registry.is_connected(server_id)
    
    def invalidate_cache(self):
        """Invalidate tool cache to force refresh."""
        self._cache_valid = False

class ToolRegistry:
    """Unified tool registry with lazy loading and plugin architecture."""
    
    def __init__(self):
        self._providers: Dict[str, ToolProvider] = {}
        self._metadata_cache: Dict[str, ToolMetadata] = {}
        self._cache_valid = False
        self._lock = asyncio.Lock()
        
        # Register default provider
        self.register_provider("default", DefaultToolProvider())
    
    def register_provider(self, name: str, provider: ToolProvider):
        """Register a tool provider."""
        self._providers[name] = provider
        self._invalidate_cache()
        logger.info(f"Registered tool provider: {name}")
    
    def unregister_provider(self, name: str):
        """Unregister a tool provider."""
        if name in self._providers:
            del self._providers[name]
            self._invalidate_cache()
            logger.info(f"Unregistered tool provider: {name}")
    
    async def _refresh_cache(self):
        """Refresh metadata cache from all providers."""
        if self._cache_valid:
            return
        
        async with self._lock:
            if self._cache_valid:  # Double-check after acquiring lock
                return
            
            self._metadata_cache.clear()
            
            for provider_name, provider in self._providers.items():
                try:
                    tools = await provider.list_tool_metadata()
                    for tool in tools:
                        if tool.id in self._metadata_cache:
                            logger.warning(f"Tool {tool.id} already registered, skipping from {provider_name}")
                            continue
                        self._metadata_cache[tool.id] = tool
                except Exception as e:
                    logger.error(f"Failed to load tools from provider {provider_name}: {e}")
            
            self._cache_valid = True
            logger.info(f"Cached {len(self._metadata_cache)} tools from {len(self._providers)} providers")
    
    def _invalidate_cache(self):
        """Invalidate the metadata cache."""
        self._cache_valid = False
    
    async def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get tool metadata by ID."""
        await self._refresh_cache()
        return self._metadata_cache.get(tool_id)
    
    async def list_tools(
        self,
        scope: Optional[AccessScope] = None,
        tool_type: Optional[ToolType] = None,
        capability: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[ToolMetadata]:
        """List tools with filtering."""
        await self._refresh_cache()
        
        tools = list(self._metadata_cache.values())
        
        if scope:
            tools = [t for t in tools if t.is_accessible_to(scope, user_id)]
        
        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]
        
        if capability:
            tools = [t for t in tools if t.has_capability(capability)]
        
        return tools
    
    async def execute_tool(self, tool_id: str, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a tool by delegating to its provider."""
        tool = await self.get_tool(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")
        
        if not tool.enabled:
            raise ValueError(f"Tool {tool_id} is disabled")
        
        # Find the provider that has this tool
        for provider in self._providers.values():
            if await provider.get_tool_metadata(tool_id):
                return await provider.execute_tool(tool_id, inputs, context or {})
        
        raise RuntimeError(f"No provider found for tool {tool_id}")
    
    async def is_tool_available(self, tool_id: str) -> bool:
        """Check if a tool is currently available."""
        for provider in self._providers.values():
            if await provider.is_available(tool_id):
                return True
        return False
    
    # Legacy compatibility methods
    
    async def get_planner_tools(self, user_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get tools in planner format (legacy compatibility)."""
        tools = await self.list_tools(scope=AccessScope.PLANNER, user_id=user_id)
        return {
            tool.id: {
                "inputs": tool.inputs or {},
                "produces": tool.produces or [],
                "description": tool.description,
            }
            for tool in tools
            if tool.inputs and tool.produces  # Only include tools with planner-specific fields
        }
    
    async def get_agent_tools(self, agent_name: str, user_id: Optional[str] = None) -> List[ToolMetadata]:
        """Get tools for a specific agent."""
        if agent_name.lower() == "conseil":
            scope = AccessScope.AGENT_CONSEIL
        elif agent_name.lower() == "vex":
            scope = AccessScope.AGENT_VEX
        else:
            scope = AccessScope.AGENT_ALL
        
        # Get agent-specific tools plus general agent tools
        agent_tools = await self.list_tools(scope=scope, user_id=user_id)
        general_tools = await self.list_tools(scope=AccessScope.AGENT_ALL, user_id=user_id)
        
        # Combine and deduplicate
        all_tools = {tool.id: tool for tool in agent_tools + general_tools}
        return list(all_tools.values())

# Global registry instance
_global_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry

async def initialize_tool_registry(mcp_registry=None) -> ToolRegistry:
    """Initialize the tool registry with all providers."""
    registry = get_tool_registry()
    
    # Register MCP provider if available
    if mcp_registry:
        registry.register_provider("mcp", MCPToolProvider(mcp_registry))
    
    return registry

# Legacy compatibility functions

async def load_planner_tools(path: Optional[Path] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Load tools for planner (legacy compatibility)."""
    registry = get_tool_registry()
    return await registry.get_planner_tools(user_id)

async def get_tools_for_agent(agent_name: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get tools for agent in legacy format."""
    registry = get_tool_registry()
    tools = await registry.get_agent_tools(agent_name, user_id)
    
    # Convert to legacy format
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "tool_type": tool.tool_type.value,
            "capabilities": list(tool.capabilities),
            "enabled": tool.enabled,
            "config": tool.config or {},
        }
        for tool in tools
    ]
