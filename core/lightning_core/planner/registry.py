# lightning_planner/registry.py
import json
from pathlib import Path
from typing import Any, Dict

# Import unified tool system
from ..tools.planner_bridge import PlannerToolBridge

# Create bridge to unified registry
_bridge = PlannerToolBridge()


class ToolRegistry:
    """Tool registry interface using unified tool system with access control"""

    @classmethod
    def load(
        cls, path: Path | None = None, user_id: str | None = None
    ) -> Dict[str, Any]:
        """Load tools available to planner from unified registry"""
        return _bridge.load(path, user_id)

    @classmethod
    def subset(cls, query: str, user_id: str | None = None) -> Dict[str, Any]:
        """Get subset of planner tools matching query"""
        return _bridge.subset(query, user_id)

    @classmethod
    def sync_to_json(cls, path: Path | None = None, user_id: str | None = None) -> None:
        """Sync unified registry to JSON file for backward compatibility only"""
        if path is None:
            path = Path(__file__).with_suffix(".tools.json")
        _bridge.sync_to_json(path, user_id)
        print(f"WARNING: JSON file sync is deprecated. Use unified registry directly.")


# ---------------------------------------------------------------------------
# External-event inventory recognised by the validator / scheduler
# Use unified event system
# ---------------------------------------------------------------------------
from ..events.registry import LegacyEventRegistryInstance

# Provide backward compatibility
EventRegistry = LegacyEventRegistryInstance
