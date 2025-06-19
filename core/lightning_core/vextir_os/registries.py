"""
Vextir OS Registries - Model, Tool, and Plan capability management
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from collections import defaultdict
import threading

from ..events.models import ExternalEvent

# Import plan-related models
from ..planner.schema import PlanModel

# Import LLM abstractions
from ..abstractions.llm import (
    LLMProvider, LLMProviderConfig, CompletionRequest, 
    CompletionResponse, StreamResponse, Message
)
from ..providers.llm import OpenAIProvider, OpenRouterProvider


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
    provider_model_id: Optional[str] = None  # Model ID as used by the provider


@dataclass
class UsageRecord:
    """Record of a single model usage"""
    model_id: str
    user_id: str
    timestamp: datetime
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    request_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageStats:
    """Aggregated usage statistics"""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    requests_by_model: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tokens_by_model: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    cost_by_model: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    
    def add_usage(self, record: UsageRecord):
        """Add a usage record to the stats"""
        self.total_requests += 1
        self.total_tokens += record.total_tokens
        self.total_cost += record.cost
        self.requests_by_model[record.model_id] += 1
        self.tokens_by_model[record.model_id] += record.total_tokens
        self.cost_by_model[record.model_id] += record.cost


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


@dataclass
class PlanSpec:
    """Plan specification - represents a plan as a first-class application"""

    id: str
    name: str
    description: str
    plan_definition: PlanModel  # The actual plan structure
    event_triggers: List[str]  # Event types this plan listens for
    capabilities: List[str]  # What this plan can do
    version: str = "1.0.0"
    author: str = "system"
    enabled: bool = True
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_trigger_events(self) -> List[str]:
        """Extract trigger events from plan definition"""
        return [
            event.name
            for event in self.plan_definition.events
            if hasattr(event, "name")
        ]


class ModelRegistry:
    """Registry for managing AI models with provider integration and usage tracking"""

    def __init__(self):
        self.models: Dict[str, ModelSpec] = {}
        self.providers: Dict[str, LLMProvider] = {}
        self.usage_records: List[UsageRecord] = []
        self.usage_stats_by_user: Dict[str, UsageStats] = defaultdict(UsageStats)
        self._usage_lock = threading.Lock()
        self._load_default_models()
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize LLM providers"""
        # Initialize OpenAI provider if API key is available
        import os
        if os.getenv("OPENAI_API_KEY"):
            openai_config = LLMProviderConfig(
                provider_type="openai",
                api_key=os.getenv("OPENAI_API_KEY"),
            )
            self.providers["openai"] = OpenAIProvider(openai_config)
            
        # Initialize OpenRouter provider if API key is available
        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_config = LLMProviderConfig(
                provider_type="openrouter",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )
            self.providers["openrouter"] = OpenRouterProvider(openrouter_config)

    def register_provider(self, provider_id: str, provider: LLMProvider):
        """Register an LLM provider"""
        self.providers[provider_id] = provider
        logging.info(f"Registered LLM provider: {provider_id}")

    def register_model(self, model: ModelSpec):
        """Register a model"""
        self.models[model.id] = model
        logging.info(f"Registered model: {model.id} ({model.provider})")

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get model by ID"""
        return self.models.get(model_id)

    def get_provider(self, provider_id: str) -> Optional[LLMProvider]:
        """Get provider by ID"""
        return self.providers.get(provider_id)

    def list_models(
        self, provider: Optional[str] = None, capability: Optional[str] = None
    ) -> List[ModelSpec]:
        """List models with optional filtering"""
        models = list(self.models.values())

        if provider:
            models = [m for m in models if m.provider == provider]

        if capability:
            models = [m for m in models if capability in m.capabilities]

        return [m for m in models if m.enabled]

    def get_models_by_capability(self, capability: str) -> List[ModelSpec]:
        """Get models that support a specific capability"""
        return [
            m
            for m in self.models.values()
            if capability in m.capabilities and m.enabled
        ]

    def get_cheapest_model(self, capability: str = "chat") -> Optional[ModelSpec]:
        """Get the cheapest model for a capability"""
        capable_models = self.get_models_by_capability(capability)
        if not capable_models:
            return None

        # Calculate total cost (input + output)
        def total_cost(model: ModelSpec) -> float:
            return model.cost_per_1k_tokens.get(
                "input", 0
            ) + model.cost_per_1k_tokens.get("output", 0)

        return min(capable_models, key=total_cost)

    async def complete(
        self, 
        model_id: str, 
        messages: List[Message], 
        user_id: Optional[str] = None,
        **kwargs
    ) -> CompletionResponse:
        """Complete a request using the specified model"""
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
            
        provider = self.get_provider(model.provider)
        if not provider:
            raise ValueError(f"Provider {model.provider} not found")
            
        # Use provider model ID if specified, otherwise use registry model ID
        provider_model_id = model.provider_model_id or model_id
        
        # Create completion request
        request = CompletionRequest(
            model=provider_model_id,
            messages=messages,
            user=user_id,
            **kwargs
        )
        
        # Make the completion request
        response = await provider.complete(request)
        
        # Track usage
        if response.usage and user_id:
            record = UsageRecord(
                model_id=model_id,
                user_id=user_id,
                timestamp=response.created,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cost=response.usage.cost or 0.0,
                request_id=response.id,
            )
            self._track_usage(record)
        
        return response

    async def stream_complete(
        self,
        model_id: str,
        messages: List[Message],
        user_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[StreamResponse]:
        """Stream a completion using the specified model"""
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
            
        provider = self.get_provider(model.provider)
        if not provider:
            raise ValueError(f"Provider {model.provider} not found")
            
        # Use provider model ID if specified, otherwise use registry model ID
        provider_model_id = model.provider_model_id or model_id
        
        # Create completion request
        request = CompletionRequest(
            model=provider_model_id,
            messages=messages,
            user=user_id,
            stream=True,
            **kwargs
        )
        
        # Stream the completion
        async for chunk in provider.stream_complete(request):
            yield chunk

    def _track_usage(self, record: UsageRecord):
        """Track usage record"""
        with self._usage_lock:
            self.usage_records.append(record)
            self.usage_stats_by_user[record.user_id].add_usage(record)

    def get_usage_stats(self, user_id: Optional[str] = None) -> UsageStats:
        """Get usage statistics for a user or all users"""
        with self._usage_lock:
            if user_id:
                return self.usage_stats_by_user.get(user_id, UsageStats())
            else:
                # Aggregate stats for all users
                total_stats = UsageStats()
                for record in self.usage_records:
                    total_stats.add_usage(record)
                return total_stats

    def get_usage_records(
        self, 
        user_id: Optional[str] = None,
        model_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[UsageRecord]:
        """Get usage records with optional filtering"""
        with self._usage_lock:
            records = self.usage_records.copy()
            
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        if model_id:
            records = [r for r in records if r.model_id == model_id]
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]
            
        return records

    def _load_default_models(self):
        """Load default model configurations"""
        # OpenAI models via OpenAI API
        gpt4o = ModelSpec(
            id="gpt-4o",
            name="GPT-4o",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling", "vision"],
            cost_per_1k_tokens={"input": 0.0025, "output": 0.01},
            context_window=128000,
            max_output_tokens=4096,
            provider_model_id="gpt-4o",
        )
        self.register_model(gpt4o)
        
        gpt4o_mini = ModelSpec(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling", "vision"],
            cost_per_1k_tokens={"input": 0.00015, "output": 0.0006},
            context_window=128000,
            max_output_tokens=16384,
            provider_model_id="gpt-4o-mini",
        )
        self.register_model(gpt4o_mini)

        gpt4_turbo = ModelSpec(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling", "vision"],
            cost_per_1k_tokens={"input": 0.01, "output": 0.03},
            context_window=128000,
            max_output_tokens=4096,
            provider_model_id="gpt-4-turbo",
        )
        self.register_model(gpt4_turbo)

        # O1 models
        o1_preview = ModelSpec(
            id="o1-preview",
            name="O1 Preview",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat"],
            cost_per_1k_tokens={"input": 0.015, "output": 0.06},
            context_window=128000,
            max_output_tokens=32768,
            provider_model_id="o1-preview",
        )
        self.register_model(o1_preview)
        
        o1_mini = ModelSpec(
            id="o1-mini",
            name="O1 Mini",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat"],
            cost_per_1k_tokens={"input": 0.003, "output": 0.012},
            context_window=128000,
            max_output_tokens=65536,
            provider_model_id="o1-mini",
        )
        self.register_model(o1_mini)
        
        o3_mini = ModelSpec(
            id="o3-mini",
            name="O3 Mini",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat"],
            cost_per_1k_tokens={"input": 0.0012, "output": 0.0048},
            context_window=128000,
            max_output_tokens=65536,
            provider_model_id="o3-mini",
        )
        self.register_model(o3_mini)
        
        # Realtime models for voice
        gpt4o_realtime = ModelSpec(
            id="gpt-4o-realtime",
            name="GPT-4o Realtime",
            provider="openai-realtime",
            endpoint="wss://api.openai.com/v1/realtime",
            capabilities=["voice", "realtime", "function_calling"],
            cost_per_1k_tokens={"input": 0.10, "output": 0.20},  # ~$0.06/min input, ~$0.24/min output
            context_window=128000,
            max_output_tokens=4096,
            provider_model_id="gpt-4o-realtime-preview-2024-12-17",
        )
        self.register_model(gpt4o_realtime)

        # Models via OpenRouter
        if "openrouter" in self.providers:
            # Claude models via OpenRouter
            claude_sonnet_4 = ModelSpec(
                id="claude-sonnet-4",
                name="Claude 3.5 Sonnet",
                provider="openrouter",
                endpoint="https://openrouter.ai/api/v1",
                capabilities=["chat", "vision"],
                cost_per_1k_tokens={"input": 0.003, "output": 0.015},
                context_window=200000,
                max_output_tokens=8192,
                provider_model_id="anthropic/claude-3.5-sonnet",
            )
            self.register_model(claude_sonnet_4)
            
            claude3_opus = ModelSpec(
                id="claude-3-opus",
                name="Claude 3 Opus",
                provider="openrouter",
                endpoint="https://openrouter.ai/api/v1",
                capabilities=["chat", "vision"],
                cost_per_1k_tokens={"input": 0.015, "output": 0.075},
                context_window=200000,
                max_output_tokens=4096,
                provider_model_id="anthropic/claude-3-opus",
            )
            self.register_model(claude3_opus)
            
            # Other models via OpenRouter
            gemini_pro_15 = ModelSpec(
                id="gemini-pro-1.5",
                name="Gemini Pro 1.5",
                provider="openrouter",
                endpoint="https://openrouter.ai/api/v1",
                capabilities=["chat", "vision"],
                cost_per_1k_tokens={"input": 0.0025, "output": 0.0075},
                context_window=2097152,  # 2M context
                max_output_tokens=8192,
                provider_model_id="google/gemini-pro-1.5",
            )
            self.register_model(gemini_pro_15)
            
            llama_3_1_405b = ModelSpec(
                id="llama-3.1-405b",
                name="Llama 3.1 405B",
                provider="openrouter",
                endpoint="https://openrouter.ai/api/v1",
                capabilities=["chat"],
                cost_per_1k_tokens={"input": 0.003, "output": 0.003},
                context_window=131072,
                max_output_tokens=8192,
                provider_model_id="meta-llama/llama-3.1-405b-instruct",
            )
            self.register_model(llama_3_1_405b)


# Note: ToolRegistry has been moved to lightning_core.tools.simple_registry
# This keeps the ToolSpec class for backward compatibility


class PlanRegistry:
    """Registry for managing plans as first-class applications"""

    def __init__(self):
        self.plans: Dict[str, PlanSpec] = {}

    def register_plan(self, plan: PlanSpec):
        """Register a plan as a first-class application"""
        self.plans[plan.id] = plan
        logging.info(f"Registered plan: {plan.id} - {plan.name}")

    def get_plan(self, plan_id: str) -> Optional[PlanSpec]:
        """Get plan by ID"""
        return self.plans.get(plan_id)

    def list_plans(self, enabled_only: bool = True) -> List[PlanSpec]:
        """List all registered plans"""
        plans = list(self.plans.values())
        if enabled_only:
            plans = [p for p in plans if p.enabled]
        return plans

    def get_plans_by_event(self, event_type: str) -> List[PlanSpec]:
        """Get plans that should be triggered by this event type"""
        return [
            plan
            for plan in self.plans.values()
            if plan.enabled and event_type in plan.event_triggers
        ]

    def get_plans_by_capability(self, capability: str) -> List[PlanSpec]:
        """Get plans that provide a specific capability"""
        return [
            plan
            for plan in self.plans.values()
            if plan.enabled and capability in plan.capabilities
        ]

    def unregister_plan(self, plan_id: str) -> bool:
        """Unregister a plan"""
        if plan_id in self.plans:
            del self.plans[plan_id]
            logging.info(f"Unregistered plan: {plan_id}")
            return True
        return False

    def update_plan(self, plan_id: str, updated_plan: PlanSpec):
        """Update an existing plan"""
        if plan_id in self.plans:
            self.plans[plan_id] = updated_plan
            logging.info(f"Updated plan: {plan_id}")
            return True
        return False


# Global registries
_global_model_registry: Optional[ModelRegistry] = None
_global_plan_registry: Optional[PlanRegistry] = None

from .drivers import DriverRegistry
from .drivers import get_driver_registry as _get_driver_registry


def get_model_registry() -> ModelRegistry:
    """Get global model registry instance"""
    global _global_model_registry
    if _global_model_registry is None:
        _global_model_registry = ModelRegistry()
    return _global_model_registry


def get_tool_registry():
    """Get global tool registry instance (redirected to simplified registry)"""
    # Redirect to the new simplified tool registry
    from ..tools import get_tool_registry as get_simplified_registry
    return get_simplified_registry()


def get_plan_registry() -> PlanRegistry:
    """Get global plan registry instance"""
    global _global_plan_registry
    if _global_plan_registry is None:
        _global_plan_registry = PlanRegistry()
    return _global_plan_registry


def get_driver_registry() -> DriverRegistry:
    """Return the global driver registry instance."""
    return _get_driver_registry()
