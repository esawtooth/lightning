"""
Simplified tool registry system for Lightning Core.
Single source of truth for all tools with plugin architecture.
"""

# Simplified registry (primary interface)
from .simple_registry import (
    ToolRegistry,
    ToolMetadata,
    ToolProvider,
    ToolType,
    AccessScope,
    get_tool_registry,
    initialize_tool_registry,
    load_planner_tools,
    get_tools_for_agent,
)

__all__ = [
    "ToolRegistry",
    "ToolMetadata", 
    "ToolProvider",
    "ToolType",
    "AccessScope",
    "get_tool_registry",
    "initialize_tool_registry",
    "load_planner_tools",
    "get_tools_for_agent",
]
