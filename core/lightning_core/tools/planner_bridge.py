"""
Bridge between unified tool registry and planner tool system.
Also handles plan registration as first-class applications in Vextir OS.
"""

import json
from pathlib import Path
from typing import Dict, Any
from .registry import get_tool_registry, AccessScope
from ..vextir_os.plan_execution_drivers import get_plan_application_manager


class PlannerToolBridge:
    """Bridge that provides planner-compatible tool registry interface"""
    
    def __init__(self):
        self._unified_registry = get_tool_registry()
        self._plan_manager = get_plan_application_manager()
    
    def load(self, path: Path = None, user_id: str = None) -> Dict[str, Any]:
        """Load tools in planner format from unified registry, filtered for planning"""
        # Get tools available to planner using access control
        planner_tools = self._unified_registry.get_planner_tools(user_id)
        
        # Convert to planner format
        return {
            tool.id: tool.to_planner_format()
            for tool in planner_tools
        }
    
    def subset(self, query: str, user_id: str = None) -> Dict[str, Any]:
        """Get subset of planner tools matching query"""
        q = query.lower()
        planner_tools = self.load(user_id=user_id)
        
        return {
            name: meta
            for name, meta in planner_tools.items()
            if q in name.lower() or q in meta.get("description", "").lower()
        }
    
    def sync_to_json(self, json_path: Path, user_id: str = None) -> None:
        """Sync current filtered planner registry to JSON file (for backward compatibility)"""
        tools = self.load(user_id=user_id)
        with json_path.open('w') as f:
            json.dump(tools, f, indent=2)
            
    async def register_plan_as_application(self, plan_json: Dict[str, Any], user_id: str = None) -> str:
        """Register a plan as a first-class application in Vextir OS"""
        return await self._plan_manager.register_plan_from_json(plan_json, user_id or "system")
        
    async def unregister_plan_application(self, plan_id: str, user_id: str = None):
        """Unregister a plan application from Vextir OS"""
        await self._plan_manager.unregister_plan(plan_id, user_id or "system")
        
    def list_plan_applications(self) -> Dict[str, Any]:
        """List all registered plan applications"""
        return {"plans": self._plan_manager.list_plan_applications()}
        
    def get_plan_application(self, plan_id: str) -> Dict[str, Any]:
        """Get details of a specific plan application"""
        plan = self._plan_manager.get_plan_application(plan_id)
        return {"plan": plan} if plan else {"error": "Plan not found"}
