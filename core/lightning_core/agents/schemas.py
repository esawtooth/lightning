"""
Agent Configuration Schemas

Defines the data structures for configuring Lightning agents.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class AgentType(Enum):
    """Types of Lightning agents"""
    CONSEIL = "conseil"      # File-based coding/task agents
    VOICE = "voice"          # Real-time voice interaction
    CHAT = "chat"            # Context-aware chat with memory
    PLANNER = "planner"      # Workflow planning agents


@dataclass
class PromptParameter:
    """A configurable parameter in a prompt template"""
    name: str
    type: str  # "string", "number", "boolean", "select"
    default_value: Any
    description: str
    options: Optional[List[str]] = None  # For select type
    required: bool = True


@dataclass
class PromptConfig:
    """Configuration for agent system prompts"""
    template: str
    parameters: Dict[str, PromptParameter] = field(default_factory=dict)
    name: str = ""
    description: str = ""
    
    def render(self, **kwargs) -> str:
        """Render the prompt template with provided parameters"""
        # Fill in default values for missing parameters
        render_params = {}
        for param_name, param in self.parameters.items():
            if param_name in kwargs:
                render_params[param_name] = kwargs[param_name]
            else:
                render_params[param_name] = param.default_value
        
        try:
            return self.template.format(**render_params)
        except KeyError as e:
            raise ValueError(f"Missing required parameter for prompt: {e}")


@dataclass
class ToolConfig:
    """Configuration for agent tools"""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False
    sandbox: bool = False
    description: str = ""


@dataclass
class EnvironmentConfig:
    """Configuration for agent operating environment"""
    # Common settings
    working_directory: str = "./"
    file_patterns: List[str] = field(default_factory=list)
    sandbox_enabled: bool = True
    
    # Context settings
    context_hub_enabled: bool = False
    conversation_memory: bool = False
    search_integration: bool = False
    
    # Voice settings  
    modalities: List[str] = field(default_factory=lambda: ["text"])
    turn_detection: str = "server_vad"
    interruption_enabled: bool = False
    
    # Planner settings
    event_types: List[str] = field(default_factory=list)
    plan_types: List[str] = field(default_factory=lambda: ["acyclic"])
    validation_enabled: bool = True
    
    # Custom settings
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Configuration for the AI model"""
    model_id: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BehaviorConfig:
    """Base configuration for agent behavior"""
    max_iterations: int = 5
    timeout_seconds: int = 300
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConseilBehaviorConfig(BehaviorConfig):
    """Conseil-specific behavior configuration"""
    approval_policy: str = "manual"  # auto, manual, guided
    job_role: str = "CODING"
    enable_thinking: bool = True
    enable_sandbox: bool = True


@dataclass
class VoiceBehaviorConfig(BehaviorConfig):
    """Voice agent behavior configuration"""
    voice_id: str = "alloy"
    response_speed: str = "normal"  # slow, normal, fast
    hooks: List[str] = field(default_factory=list)  # Hook implementation names
    compliance_mode: Optional[str] = None  # healthcare, finance, etc


@dataclass
class ChatBehaviorConfig(BehaviorConfig):
    """Chat agent behavior configuration"""
    memory_strategy: str = "context_hub"
    proactive_search: bool = True
    auto_document_updates: bool = True
    search_before_response: bool = True


@dataclass
class PlannerBehaviorConfig(BehaviorConfig):
    """Planner agent behavior configuration"""
    planning_model: str = "o3-mini"
    max_retries: int = 4
    validation_strict: bool = True
    auto_execute: bool = False


@dataclass
class AgentConfig:
    """Base configuration for all Lightning agents"""
    id: str
    name: str
    type: AgentType
    description: str
    
    # Core components
    system_prompt: PromptConfig
    tools: List[ToolConfig]
    environment: EnvironmentConfig
    model_config: ModelConfig
    behavior_config: BehaviorConfig
    
    # Metadata
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    is_default: bool = False
    is_system: bool = False
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        def convert_value(value):
            if isinstance(value, datetime):
                return value.isoformat()
            elif isinstance(value, Enum):
                return value.value
            elif hasattr(value, '__dict__'):
                return {k: convert_value(v) for k, v in value.__dict__.items()}
            elif isinstance(value, list):
                return [convert_value(item) for item in value]
            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            else:
                return value
        
        return convert_value(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """Create from dictionary"""
        # Convert type back to enum
        if "type" in data and isinstance(data["type"], str):
            data["type"] = AgentType(data["type"])
        
        # Convert datetime strings back
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        
        # Convert nested objects
        if "system_prompt" in data and isinstance(data["system_prompt"], dict):
            prompt_data = data["system_prompt"]
            # Convert parameters
            if "parameters" in prompt_data:
                params = {}
                for name, param_data in prompt_data["parameters"].items():
                    params[name] = PromptParameter(**param_data)
                prompt_data["parameters"] = params
            data["system_prompt"] = PromptConfig(**prompt_data)
        
        if "tools" in data and isinstance(data["tools"], list):
            data["tools"] = [ToolConfig(**tool) if isinstance(tool, dict) else tool 
                           for tool in data["tools"]]
        
        if "environment" in data and isinstance(data["environment"], dict):
            data["environment"] = EnvironmentConfig(**data["environment"])
        
        if "model_config" in data and isinstance(data["model_config"], dict):
            data["model_config"] = ModelConfig(**data["model_config"])
        
        if "behavior_config" in data and isinstance(data["behavior_config"], dict):
            # Determine behavior config type based on agent type
            agent_type = data.get("type", AgentType.CHAT)
            if agent_type == AgentType.CONSEIL:
                data["behavior_config"] = ConseilBehaviorConfig(**data["behavior_config"])
            elif agent_type == AgentType.VOICE:
                data["behavior_config"] = VoiceBehaviorConfig(**data["behavior_config"])
            elif agent_type == AgentType.CHAT:
                data["behavior_config"] = ChatBehaviorConfig(**data["behavior_config"])
            elif agent_type == AgentType.PLANNER:
                data["behavior_config"] = PlannerBehaviorConfig(**data["behavior_config"])
            else:
                data["behavior_config"] = BehaviorConfig(**data["behavior_config"])
        
        return cls(**data)


@dataclass
class ConseilAgentConfig(AgentConfig):
    """Conseil agent configuration with specialized defaults"""
    behavior_config: ConseilBehaviorConfig = field(default_factory=ConseilBehaviorConfig)
    
    def __post_init__(self):
        self.type = AgentType.CONSEIL
        if not self.tools:
            self.tools = [
                ToolConfig("shell", enabled=True, sandbox=True, approval_required=True),
                ToolConfig("web_search", enabled=True),
                ToolConfig("apply_patch", enabled=True, approval_required=True),
                ToolConfig("get_url", enabled=True),
            ]
        if not self.environment.file_patterns:
            self.environment.file_patterns = ["*.py", "*.js", "*.ts", "*.java", "*.cpp", "*.go", "*.rs"]


@dataclass
class VoiceAgentConfig(AgentConfig):
    """Voice agent configuration with specialized defaults"""
    behavior_config: VoiceBehaviorConfig = field(default_factory=VoiceBehaviorConfig)
    
    def __post_init__(self):
        self.type = AgentType.VOICE
        if not self.tools:
            self.tools = [
                ToolConfig("web_search", enabled=True),
                ToolConfig("calendar", enabled=False),
                ToolConfig("email", enabled=False),
            ]
        self.environment.modalities = ["audio", "text"]
        self.environment.turn_detection = "server_vad"
        self.environment.interruption_enabled = True


@dataclass  
class ChatAgentConfig(AgentConfig):
    """Chat agent configuration with specialized defaults"""
    behavior_config: ChatBehaviorConfig = field(default_factory=ChatBehaviorConfig)
    
    def __post_init__(self):
        self.type = AgentType.CHAT
        if not self.tools:
            self.tools = [
                ToolConfig("search_user_context", enabled=True),
                ToolConfig("read_document", enabled=True),
                ToolConfig("write_document", enabled=True),
                ToolConfig("list_documents", enabled=True),
            ]
        self.environment.context_hub_enabled = True
        self.environment.conversation_memory = True
        self.environment.search_integration = True


@dataclass
class PlannerAgentConfig(AgentConfig):
    """Planner agent configuration with specialized defaults"""
    behavior_config: PlannerBehaviorConfig = field(default_factory=PlannerBehaviorConfig)
    
    def __post_init__(self):
        self.type = AgentType.PLANNER
        self.environment.event_types = ["user.input", "schedule.trigger"] 
        self.environment.plan_types = ["acyclic", "reactive"]
        self.environment.validation_enabled = True
        self.model_config.model_id = "o3-mini"