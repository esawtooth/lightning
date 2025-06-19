"""Model Context Protocol (MCP) integration for Lightning.

This module provides safe and extensible integration of MCP servers as tools
for agents in the Lightning ecosystem.
"""

from .client import MCPClient, MCPConnectionType, MCPTool
from .registry import MCPRegistry, MCPServerConfig
from .proxy import MCPSecurityProxy, ValidationResult
from .sandbox import MCPSandbox, SandboxConfig, SANDBOX_PRESETS
from .adapter import MCPToolAdapter, MCPToolRegistry
from .drivers import MCPDriver

__all__ = [
    "MCPClient",
    "MCPConnectionType",
    "MCPTool",
    "MCPRegistry",
    "MCPServerConfig",
    "MCPSecurityProxy",
    "ValidationResult",
    "MCPSandbox",
    "SandboxConfig",
    "SANDBOX_PRESETS",
    "MCPToolAdapter",
    "MCPToolRegistry",
    "MCPDriver",
]