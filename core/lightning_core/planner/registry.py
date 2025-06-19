# lightning_planner/registry.py
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

# Import simplified tool system
from ..tools import load_planner_tools

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Tool registry interface for planner using simplified tool system"""

    @classmethod
    def load(
        cls, path: Path | None = None, user_id: str | None = None
    ) -> Dict[str, Any]:
        """Load tools available to planner from simplified registry"""
        # Handle both sync and async contexts properly
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context - need to run in thread pool
                import concurrent.futures
                import threading
                
                def run_async():
                    return asyncio.run(load_planner_tools(path, user_id))
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async)
                    return future.result(timeout=30)
                    
            except RuntimeError:
                # No running loop - we can run directly
                return asyncio.run(load_planner_tools(path, user_id))
                
        except Exception as e:
            # Fallback to synchronous loading with hardcoded tools
            logger.warning(f"Failed to load tools from registry: {e}, using fallback")
            return cls._get_fallback_tools()

    @classmethod
    def subset(cls, query: str, user_id: str | None = None) -> Dict[str, Any]:
        """Get subset of planner tools matching query"""
        all_tools = cls.load(user_id=user_id)
        
        # Simple query matching - match against tool ID, name, or description
        query_lower = query.lower()
        return {
            tool_id: tool_data
            for tool_id, tool_data in all_tools.items()
            if (query_lower in tool_id.lower() or 
                query_lower in tool_data.get("description", "").lower())
        }

    @classmethod
    def sync_to_json(cls, path: Path | None = None, user_id: str | None = None) -> None:
        """Sync registry to JSON file for backward compatibility only"""
        if path is None:
            path = Path(__file__).with_suffix(".tools.json")
        
        tools = cls.load(user_id=user_id)
        with path.open("w") as f:
            json.dump(tools, f, indent=2)
        print(f"WARNING: JSON file sync is deprecated. Use simplified registry directly.")

    @classmethod
    def _get_fallback_tools(cls) -> Dict[str, Any]:
        """Fallback tools when registry loading fails"""
        return {
            "agent.conseil": {
                "inputs": {"objective": "string", "additional_context": "string"},
                "produces": ["event.agent.conseil.start"],
                "description": "Research and bash execution agent with context access",
            },
            "agent.vex": {
                "inputs": {"objective": "string", "phone_number": "string", "additional_context": "string"},
                "produces": ["event.agent.vex.start"], 
                "description": "Voice interaction agent for phone calls",
            },
            "llm.summarize": {
                "inputs": {"text": "string", "style": "string"},
                "produces": ["event.summary_ready"],
                "description": "Summarize text using GPT-4 Turbo",
            },
            "llm.general_prompt": {
                "inputs": {"system_prompt": "string", "user_prompt": "string", "model": "string"},
                "produces": ["event.llm_response"],
                "description": "General LLM prompt processing",
            },
            "email.send": {
                "inputs": {"to": "string", "subject": "string", "body": "string", "attachments": "string"},
                "produces": ["event.email.sent"],
                "description": "Send email with attachments",
            },
            "chat.sendTeamsMessage": {
                "inputs": {"channel_id": "string", "content": "string"},
                "produces": ["event.teams_message_sent"],
                "description": "Send Microsoft Teams message",
            },
            "cron.configure": {
                "inputs": {"plan_id": "string", "cron_expression": "string", "description": "string"},
                "produces": ["event.cron.configured"],
                "description": "Configure scheduled plan execution",
            },
            "event.schedule.create": {
                "inputs": {"title": "string", "cron": "string", "start_time": "datetime", "end_time": "datetime"},
                "produces": ["event.scheduled_event"],
                "description": "Create scheduled events",
            },
            "event.timer.start": {
                "inputs": {"duration": "integer"},
                "produces": ["event.timed_event"],
                "description": "Create timed events",
            }
        }


# ---------------------------------------------------------------------------
# External-event inventory recognised by the validator / scheduler
# Use unified event system
# ---------------------------------------------------------------------------
from ..events.registry import LegacyEventRegistryInstance

# Provide backward compatibility
EventRegistry = LegacyEventRegistryInstance
