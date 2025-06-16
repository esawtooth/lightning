"""
Vextir OS Registries - Model and Tool capability management
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum


@dataclass
class ModelSpec:
    """Model specification and capabilities"""
    id: str
    name: str
    provider: str
    endpoint: str
    capabilities: List[str]  # ["chat", "function_calling", "vision", "embedding"]
    cost_per_1k_tokens: Dict[str, float]  # {"input": 0.03, "output": 0.06}
    context_window: int = 4096
    max_output_tokens: int = 2048
    supports_streaming: bool = True
    model_family: str = "gpt"
    version: str = "1.0"
    enabled: bool = True


@dataclass
class ToolSpec:
    """Tool specification and capabilities"""
    id: str
    name: str
    description: str
    tool_type: str  # "mcp_server", "native", "api", "function"
    capabilities: List[str]
    endpoint: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class ModelRegistry:
    """Registry for managing AI models"""
    
    def __init__(self):
        self.models: Dict[str, ModelSpec] = {}
        self._load_default_models()
        
    def register_model(self, model: ModelSpec):
        """Register a model"""
        self.models[model.id] = model
        logging.info(f"Registered model: {model.id} ({model.provider})")
        
    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get model by ID"""
        return self.models.get(model_id)
        
    def list_models(self, provider: Optional[str] = None, capability: Optional[str] = None) -> List[ModelSpec]:
        """List models with optional filtering"""
        models = list(self.models.values())
        
        if provider:
            models = [m for m in models if m.provider == provider]
            
        if capability:
            models = [m for m in models if capability in m.capabilities]
            
        return [m for m in models if m.enabled]
        
    def get_models_by_capability(self, capability: str) -> List[ModelSpec]:
        """Get models that support a specific capability"""
        return [m for m in self.models.values() if capability in m.capabilities and m.enabled]
        
    def get_cheapest_model(self, capability: str = "chat") -> Optional[ModelSpec]:
        """Get the cheapest model for a capability"""
        capable_models = self.get_models_by_capability(capability)
        if not capable_models:
            return None
            
        # Calculate total cost (input + output)
        def total_cost(model: ModelSpec) -> float:
            return model.cost_per_1k_tokens.get("input", 0) + model.cost_per_1k_tokens.get("output", 0)
            
        return min(capable_models, key=total_cost)
        
    def _load_default_models(self):
        """Load default model configurations"""
        # OpenAI models
        gpt4 = ModelSpec(
            id="gpt-4",
            name="GPT-4",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling"],
            cost_per_1k_tokens={"input": 0.03, "output": 0.06},
            context_window=8192,
            max_output_tokens=4096
        )
        self.register_model(gpt4)
        
        gpt4_turbo = ModelSpec(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling", "vision"],
            cost_per_1k_tokens={"input": 0.01, "output": 0.03},
            context_window=128000,
            max_output_tokens=4096
        )
        self.register_model(gpt4_turbo)
        
        gpt35_turbo = ModelSpec(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling"],
            cost_per_1k_tokens={"input": 0.0015, "output": 0.002},
            context_window=16384,
            max_output_tokens=4096
        )
        self.register_model(gpt35_turbo)
        
        # Anthropic models
        claude3_opus = ModelSpec(
            id="claude-3-opus",
            name="Claude 3 Opus",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.015, "output": 0.075},
            context_window=200000,
            max_output_tokens=4096
        )
        self.register_model(claude3_opus)
        
        claude3_sonnet = ModelSpec(
            id="claude-3-sonnet",
            name="Claude 3 Sonnet",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.003, "output": 0.015},
            context_window=200000,
            max_output_tokens=4096
        )
        self.register_model(claude3_sonnet)
        
        claude3_haiku = ModelSpec(
            id="claude-3-haiku",
            name="Claude 3 Haiku",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.00025, "output": 0.00125},
            context_window=200000,
            max_output_tokens=4096
        )
        self.register_model(claude3_haiku)


class ToolRegistry:
    """Registry for managing tools and capabilities"""
    
    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}
        self._load_default_tools()
        
    def register_tool(self, tool: ToolSpec):
        """Register a tool"""
        self.tools[tool.id] = tool
        logging.info(f"Registered tool: {tool.id} ({tool.tool_type})")
        
    def get_tool(self, tool_id: str) -> Optional[ToolSpec]:
        """Get tool by ID"""
        return self.tools.get(tool_id)
        
    def list_tools(self, tool_type: Optional[str] = None, capability: Optional[str] = None) -> List[ToolSpec]:
        """List tools with optional filtering"""
        tools = list(self.tools.values())
        
        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]
            
        if capability:
            tools = [t for t in tools if capability in t.capabilities]
            
        return [t for t in tools if t.enabled]
        
    def get_tools_by_capability(self, capability: str) -> List[ToolSpec]:
        """Get tools that provide a specific capability"""
        return [t for t in self.tools.values() if capability in t.capabilities and t.enabled]
        
    def _load_default_tools(self):
        """Load default tool configurations"""
        # Web search tool
        web_search = ToolSpec(
            id="web_search",
            name="Web Search",
            description="Search the web for information",
            tool_type="mcp_server",
            capabilities=["search", "scrape"],
            endpoint="github.com/example/search-mcp",
            config={"max_results": 10}
        )
        self.register_tool(web_search)
        
        # Context hub tools
        context_read = ToolSpec(
            id="context_read",
            name="Context Read",
            description="Read from user's context hub",
            tool_type="native",
            capabilities=["context_read", "search"],
            config={"handler": "context_hub.read"}
        )
        self.register_tool(context_read)
        
        context_write = ToolSpec(
            id="context_write",
            name="Context Write",
            description="Write to user's context hub",
            tool_type="native",
            capabilities=["context_write"],
            config={"handler": "context_hub.write"}
        )
        self.register_tool(context_write)
        
        # Email tools
        email_read = ToolSpec(
            id="email_read",
            name="Email Read",
            description="Read emails from connected providers",
            tool_type="native",
            capabilities=["email_read"],
            config={"handler": "email_connector.read"}
        )
        self.register_tool(email_read)
        
        email_send = ToolSpec(
            id="email_send",
            name="Email Send",
            description="Send emails via connected providers",
            tool_type="native",
            capabilities=["email_send"],
            config={"handler": "email_connector.send"}
        )
        self.register_tool(email_send)
        
        # Calendar tools
        calendar_read = ToolSpec(
            id="calendar_read",
            name="Calendar Read",
            description="Read calendar events",
            tool_type="native",
            capabilities=["calendar_read"],
            config={"handler": "calendar_connector.read"}
        )
        self.register_tool(calendar_read)
        
        calendar_create = ToolSpec(
            id="calendar_create",
            name="Calendar Create",
            description="Create calendar events",
            tool_type="native",
            capabilities=["calendar_create"],
            config={"handler": "calendar_connector.create"}
        )
        self.register_tool(calendar_create)
        
        # GitHub tool
        github_tool = ToolSpec(
            id="github_tool",
            name="GitHub Integration",
            description="GitHub repository management",
            tool_type="mcp_server",
            capabilities=["github_issue", "github_pr", "github_repo"],
            endpoint="github.com/modelcontextprotocol/servers/github",
            config={"requires_auth": True}
        )
        self.register_tool(github_tool)


# Global registries
_global_model_registry: Optional[ModelRegistry] = None
_global_tool_registry: Optional[ToolRegistry] = None

from .drivers import DriverRegistry, get_driver_registry as _get_driver_registry


def get_model_registry() -> ModelRegistry:
    """Get global model registry instance"""
    global _global_model_registry
    if _global_model_registry is None:
        _global_model_registry = ModelRegistry()
    return _global_model_registry


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry instance"""
    global _global_tool_registry
    if _global_tool_registry is None:
        _global_tool_registry = ToolRegistry()
    return _global_tool_registry


def get_driver_registry() -> DriverRegistry:
    """Return the global driver registry instance."""
    return _get_driver_registry()
