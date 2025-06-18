"""
Bridge between unified tool registry and VextirOS tool system.
"""

from typing import Any, Dict, List, Optional

from .registry import ToolSpec, ToolType, get_tool_registry


class VextirToolBridge:
    """Bridge that provides VextirOS-compatible tool registry interface"""

    def __init__(self):
        self._unified_registry = get_tool_registry()

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all tools in VextirOS format"""
        return self._unified_registry.get_vextir_tools()

    def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get specific tool in VextirOS format"""
        tool = self._unified_registry.get_tool(tool_id)
        return tool.to_vextir_format() if tool else None

    def list_tools(
        self, tool_type: Optional[str] = None, capability: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List tools with filtering in VextirOS format"""
        tool_type_enum = ToolType(tool_type) if tool_type else None
        tools = self._unified_registry.list_tools(
            tool_type=tool_type_enum, capability=capability
        )
        return [tool.to_vextir_format() for tool in tools]

    def get_tools_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Get tools that provide a specific capability"""
        tools = self._unified_registry.list_tools(capability=capability)
        return [tool.to_vextir_format() for tool in tools]

    def register_tool_from_vextir(self, vextir_tool_data: Dict[str, Any]) -> None:
        """Register a tool from VextirOS format"""
        tool = ToolSpec(
            id=vextir_tool_data["id"],
            name=vextir_tool_data["name"],
            description=vextir_tool_data["description"],
            tool_type=ToolType(vextir_tool_data["tool_type"]),
            capabilities=vextir_tool_data.get("capabilities", []),
            endpoint=vextir_tool_data.get("endpoint"),
            config=vextir_tool_data.get("config", {}),
            resource_requirements=vextir_tool_data.get("resource_requirements", {}),
            enabled=vextir_tool_data.get("enabled", True),
        )
        self._unified_registry.register_tool(tool)
