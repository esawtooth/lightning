"""Tool models for Lightning Core."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ToolType(Enum):
    """Types of tools in the system."""
    AGENT = "agent"
    LLM = "llm"
    NATIVE = "native"
    MCP = "mcp"
    API = "api"


class ToolScope(Enum):
    """Access scopes for tools."""
    PLANNER = "planner"
    AGENT_CONSEIL = "agent_conseil"
    AGENT_VEX = "agent_vex"
    AGENT_ALL = "agent_all"
    SYSTEM = "system"
    USER = "user"


class ToolCategory(Enum):
    """Tool categories."""
    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    RESEARCH = "research"
    DEVELOPMENT = "development"
    SYSTEM = "system"
    UTILITY = "utility"


@dataclass
class Tool:
    """Tool definition."""
    id: str
    name: str
    description: str
    tool_type: ToolType
    category: ToolCategory
    scopes: Set[ToolScope] = field(default_factory=set)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)