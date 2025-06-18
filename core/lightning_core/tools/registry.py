"""
Unified tool registry that bridges planner and VextirOS tool systems.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


class AccessScope(Enum):
    """Defines where a tool can be accessed"""

    PLANNER = "planner"  # Available to workflow planner
    AGENT_CONSEIL = "agent_conseil"  # Available to Conseil agent
    AGENT_VEX = "agent_vex"  # Available to Vex agent
    AGENT_ALL = "agent_all"  # Available to all agents
    SYSTEM = "system"  # System-level tools
    USER = "user"  # User-facing tools


@dataclass
class AccessControl:
    """Defines access control for tools"""

    scopes: Set[AccessScope] = field(default_factory=set)
    user_permissions: Dict[str, bool] = field(
        default_factory=dict
    )  # user_id -> enabled
    requires_auth: bool = False
    admin_only: bool = False

    def is_accessible_to(
        self, scope: AccessScope, user_id: Optional[str] = None
    ) -> bool:
        """Check if tool is accessible in given scope for user"""
        if self.admin_only and user_id and not self._is_admin(user_id):
            return False

        if scope not in self.scopes:
            return False

        if user_id and user_id in self.user_permissions:
            return self.user_permissions[user_id]

        return True

    def _is_admin(self, user_id: str) -> bool:
        """Check if user is admin (placeholder implementation)"""
        # TODO: Implement proper admin check
        return user_id.endswith("_admin")


class ToolType(Enum):
    """Types of tools available in the system"""

    NATIVE = "native"  # Built-in Lightning Core tools
    MCP_SERVER = "mcp_server"  # MCP server tools
    API = "api"  # External API tools
    FUNCTION = "function"  # Function-based tools
    AGENT = "agent"  # Agent-based tools


@dataclass
class ToolSpec:
    """Unified tool specification"""

    id: str
    name: str
    description: str
    tool_type: ToolType

    # Planner-specific fields
    inputs: Dict[str, str] = field(default_factory=dict)  # {arg_name: type}
    produces: List[str] = field(default_factory=list)  # Events produced

    # VextirOS-specific fields
    capabilities: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    resource_requirements: Dict[str, Any] = field(default_factory=dict)

    # Access control
    access_control: AccessControl = field(default_factory=AccessControl)

    # Common fields
    enabled: bool = True
    version: str = "1.0"
    tags: Set[str] = field(default_factory=set)

    def to_planner_format(self) -> Dict[str, Any]:
        """Convert to planner registry format"""
        return {
            "inputs": self.inputs,
            "produces": self.produces,
            "description": self.description,
        }

    def to_vextir_format(self) -> Dict[str, Any]:
        """Convert to VextirOS registry format"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type.value,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "config": self.config,
            "resource_requirements": self.resource_requirements,
            "enabled": self.enabled,
        }


class UnifiedToolRegistry:
    """Unified registry managing tools for both planner and VextirOS"""

    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}
        self._load_default_tools()

    def register_tool(self, tool: ToolSpec) -> None:
        """Register a tool in the unified registry"""
        self.tools[tool.id] = tool
        logging.info(f"Registered unified tool: {tool.id} ({tool.tool_type.value})")

    def get_tool(self, tool_id: str) -> Optional[ToolSpec]:
        """Get tool by ID"""
        return self.tools.get(tool_id)

    def list_tools(
        self,
        tool_type: Optional[ToolType] = None,
        capability: Optional[str] = None,
        access_scope: Optional[AccessScope] = None,
        user_id: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[ToolSpec]:
        """List tools with optional filtering"""
        tools = list(self.tools.values())

        if enabled_only:
            tools = [t for t in tools if t.enabled]

        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]

        if capability:
            tools = [t for t in tools if capability in t.capabilities]

        if access_scope:
            tools = [
                t
                for t in tools
                if t.access_control.is_accessible_to(access_scope, user_id)
            ]

        return tools

    def get_tools_for_scope(
        self, scope: AccessScope, user_id: Optional[str] = None
    ) -> List[ToolSpec]:
        """Get all tools accessible in a specific scope"""
        return self.list_tools(access_scope=scope, user_id=user_id)

    def get_planner_tools(self, user_id: Optional[str] = None) -> List[ToolSpec]:
        """Get tools available to the planner"""
        return self.get_tools_for_scope(AccessScope.PLANNER, user_id)

    def get_agent_tools(
        self, agent_name: str, user_id: Optional[str] = None
    ) -> List[ToolSpec]:
        """Get tools available to a specific agent"""
        if agent_name.lower() == "conseil":
            scope = AccessScope.AGENT_CONSEIL
        elif agent_name.lower() == "vex":
            scope = AccessScope.AGENT_VEX
        else:
            scope = AccessScope.AGENT_ALL

        # Get agent-specific tools plus general agent tools
        agent_tools = self.get_tools_for_scope(scope, user_id)
        general_tools = self.get_tools_for_scope(AccessScope.AGENT_ALL, user_id)

        # Combine and deduplicate
        all_tools = {tool.id: tool for tool in agent_tools + general_tools}
        return list(all_tools.values())

    def get_planner_registry(self) -> Dict[str, Any]:
        """Get tools in planner registry format"""
        return {
            tool.id: tool.to_planner_format()
            for tool in self.tools.values()
            if tool.enabled
        }

    def get_vextir_tools(self) -> List[Dict[str, Any]]:
        """Get tools in VextirOS format"""
        return [tool.to_vextir_format() for tool in self.tools.values() if tool.enabled]

    def sync_from_planner_json(self, json_path: Path) -> None:
        """Sync tools from existing planner JSON registry"""
        try:
            with json_path.open() as f:
                planner_tools = json.load(f)

            for tool_id, tool_data in planner_tools.items():
                if tool_id not in self.tools:
                    # Create new tool from planner data
                    tool = ToolSpec(
                        id=tool_id,
                        name=tool_id.replace(".", " ").title(),
                        description=tool_data.get("description", ""),
                        tool_type=self._infer_tool_type(tool_id),
                        inputs=tool_data.get("inputs", {}),
                        produces=tool_data.get("produces", []),
                        capabilities=self._infer_capabilities(tool_id, tool_data),
                        access_control=AccessControl(scopes={AccessScope.PLANNER}),
                    )
                    self.register_tool(tool)
                # Note: Do NOT override existing unified registry tools with JSON data
                # The unified registry takes precedence over legacy JSON

        except Exception as e:
            logging.error(f"Failed to sync from planner JSON: {e}")

    def sync_from_vextir_registry(self, vextir_registry) -> None:
        """Sync tools from VextirOS registry"""
        try:
            for tool_id, vextir_tool in vextir_registry.tools.items():
                if tool_id not in self.tools:
                    # Create new tool from VextirOS data
                    tool = ToolSpec(
                        id=vextir_tool.id,
                        name=vextir_tool.name,
                        description=vextir_tool.description,
                        tool_type=ToolType(vextir_tool.tool_type),
                        capabilities=vextir_tool.capabilities,
                        endpoint=vextir_tool.endpoint,
                        config=vextir_tool.config,
                        resource_requirements=vextir_tool.resource_requirements,
                        enabled=vextir_tool.enabled,
                    )
                    self.register_tool(tool)
                else:
                    # Update existing tool with VextirOS data
                    existing_tool = self.tools[tool_id]
                    existing_tool.capabilities = vextir_tool.capabilities
                    existing_tool.endpoint = vextir_tool.endpoint
                    existing_tool.config = vextir_tool.config
                    existing_tool.resource_requirements = (
                        vextir_tool.resource_requirements
                    )

        except Exception as e:
            logging.error(f"Failed to sync from VextirOS registry: {e}")

    def _infer_tool_type(self, tool_id: str) -> ToolType:
        """Infer tool type from tool ID"""
        if tool_id.startswith("agent."):
            return ToolType.AGENT
        elif tool_id.startswith("llm."):
            return ToolType.FUNCTION
        elif tool_id.startswith("email.") or tool_id.startswith("chat."):
            return ToolType.NATIVE
        elif tool_id.startswith("web."):
            return ToolType.MCP_SERVER
        else:
            return ToolType.NATIVE

    def _infer_capabilities(self, tool_id: str, tool_data: Dict[str, Any]) -> List[str]:
        """Infer capabilities from tool ID and data"""
        capabilities = []

        # Infer from tool ID
        if "email" in tool_id:
            capabilities.extend(["email_send", "email_read"])
        elif "web" in tool_id:
            capabilities.extend(["web_search", "web_scrape"])
        elif "llm" in tool_id:
            capabilities.extend(["text_generation", "summarization"])
        elif "agent" in tool_id:
            capabilities.extend(["task_execution", "reasoning"])
        elif "cron" in tool_id:
            capabilities.extend(["scheduling", "automation"])

        # Infer from produces
        produces = tool_data.get("produces", [])
        for event in produces:
            if "email" in event:
                capabilities.append("email_send")
            elif "search" in event:
                capabilities.append("web_search")
            elif "summary" in event:
                capabilities.append("summarization")

        return list(set(capabilities))  # Remove duplicates

    def _load_default_tools(self) -> None:
        """Load default unified tool definitions"""

        # Agent tools - Available to planner for workflow orchestration
        conseil_agent = ToolSpec(
            id="agent.conseil",
            name="Conseil Agent",
            description="Requests the Conseil agent to start working on an objective. The agent has access to bash in an internet connected container, and the users context-hub data.",
            tool_type=ToolType.AGENT,
            inputs={"objective": "string", "additional_context": "string"},
            produces=["event.agent.conseil.start"],
            capabilities=[
                "task_execution",
                "bash_access",
                "context_access",
                "reasoning",
            ],
            access_control=AccessControl(scopes={AccessScope.PLANNER}),
        )
        self.register_tool(conseil_agent)

        vex_agent = ToolSpec(
            id="agent.vex",
            name="Vex Agent",
            description="Requests the vex agent to make a phone call and achieve an objective. The agent has access to users context-hub data.",
            tool_type=ToolType.AGENT,
            inputs={
                "objective": "string",
                "phone_number": "string",
                "additional_context": "string",
            },
            produces=["event.agent.vex.start"],
            capabilities=["phone_calls", "context_access", "voice_interaction"],
            access_control=AccessControl(scopes={AccessScope.PLANNER}),
        )
        self.register_tool(vex_agent)

        # LLM tools - Available to planner and agents
        llm_summarize = ToolSpec(
            id="llm.summarize",
            name="LLM Summarize",
            description="Call GPT‑4 Turbo to summarise text",
            tool_type=ToolType.FUNCTION,
            inputs={"text": "string", "style": "string"},
            produces=["event.summary_ready"],
            capabilities=["text_generation", "summarization"],
            access_control=AccessControl(
                scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL}
            ),
        )
        self.register_tool(llm_summarize)

        llm_general = ToolSpec(
            id="llm.general_prompt",
            name="LLM General Prompt",
            description="Send a general prompt to LLM for processing",
            tool_type=ToolType.FUNCTION,
            inputs={
                "system_prompt": "string",
                "user_prompt": "string",
                "model": "string",
            },
            produces=["event.llm_response"],
            capabilities=["text_generation", "reasoning", "multi_model"],
            access_control=AccessControl(scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL}),
        )
        self.register_tool(llm_general)

        # Communication tools - Available to planner and agents  
        teams_chat = ToolSpec(
            id="chat.sendTeamsMessage",
            name="Teams Message",
            description="Send a message to a Microsoft Teams channel",
            tool_type=ToolType.NATIVE,
            inputs={"channel_id": "string", "content": "string"},
            produces=["event.teams_message_sent"],
            capabilities=["team_communication", "messaging"],
            config={"handler": "teams_connector.send"},
            access_control=AccessControl(scopes={AccessScope.PLANNER, AccessScope.AGENT_ALL}),
        )
        self.register_tool(teams_chat)

        email_send = ToolSpec(
            id="email.send",
            name="Email Send",
            description="Send an email to specified recipients with subject, body and optional attachments",
            tool_type=ToolType.NATIVE,
            inputs={
                "to": "string",
                "subject": "string",
                "body": "string",
                "attachments": "string",
            },
            produces=["event.email.sent"],
            capabilities=["email_send", "communication"],
            config={"handler": "email_connector.send"},
            access_control=AccessControl(scopes={AccessScope.AGENT_ALL}),
        )
        self.register_tool(email_send)

        # Web tools - Available to agents only (not planner)
        web_search = ToolSpec(
            id="web.search",
            name="Web Search",
            description="Search the web for information using specified query with optional result limits and source filtering",
            tool_type=ToolType.MCP_SERVER,
            inputs={
                "query": "string",
                "max_results": "string",
                "source_filter": "string",
            },
            produces=["event.search.complete"],
            capabilities=["web_search", "information_retrieval"],
            endpoint="github.com/example/search-mcp",
            access_control=AccessControl(scopes={AccessScope.AGENT_ALL}),
        )
        self.register_tool(web_search)

        # Scheduling tools - Available to planner only
        cron_configure = ToolSpec(
            id="cron.configure",
            name="Cron Configure",
            description="Configure a cron job that will emit events for the specified plan at scheduled intervals",
            tool_type=ToolType.NATIVE,
            inputs={
                "plan_id": "string",
                "cron_expression": "string",
                "description": "string",
            },
            produces=["event.cron.configured"],
            capabilities=["scheduling", "automation", "cron_management"],
            config={"handler": "scheduler.configure_cron"},
            access_control=AccessControl(scopes={AccessScope.PLANNER}),
        )
        self.register_tool(cron_configure)

        # Event scheduling tools - Available to planner only
        event_schedule = ToolSpec(
            id="event.schedule.create",
            name="Event Schedule Create",
            description="Produces events associated with a cron job",
            tool_type=ToolType.NATIVE,
            inputs={
                "title": "string",
                "cron": "string",
                "start_time": "datetime",
                "end_time": "datetime",
            },
            produces=["event.scheduled_event"],
            capabilities=["scheduling", "event_management"],
            access_control=AccessControl(scopes={AccessScope.PLANNER}),
        )
        self.register_tool(event_schedule)

        event_timer = ToolSpec(
            id="event.timer.start",
            name="Event Timer Start",
            description="Produces an event after a specified duration",
            tool_type=ToolType.NATIVE,
            inputs={"duration": "integer"},
            produces=["event.timed_event"],
            capabilities=["timing", "event_management"],
            access_control=AccessControl(scopes={AccessScope.PLANNER}),
        )
        self.register_tool(event_timer)


# Global registry instance
_global_registry: Optional[UnifiedToolRegistry] = None


def get_tool_registry() -> UnifiedToolRegistry:
    """Get the global unified tool registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = UnifiedToolRegistry()

        # Sync with existing registries
        try:
            # Sync from planner JSON
            planner_json_path = (
                Path(__file__).parent.parent / "planner" / "registry.tools.json"
            )
            if planner_json_path.exists():
                _global_registry.sync_from_planner_json(planner_json_path)

            # Sync from VextirOS registry
            from ..vextir_os.registries import get_tool_registry as get_vextir_registry

            vextir_registry = get_vextir_registry()
            _global_registry.sync_from_vextir_registry(vextir_registry)

        except Exception as e:
            logging.error(f"Failed to sync registries during initialization: {e}")

    return _global_registry
