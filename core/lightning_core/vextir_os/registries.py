"""
Vextir OS Registries - Model, Tool, and Plan capability management
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..events.models import ExternalEvent

# Import plan-related models
from ..planner.schema import PlanModel


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
    """Registry for managing AI models"""

    def __init__(self):
        self.models: Dict[str, ModelSpec] = {}
        self._load_default_models()

    def register_model(self, model: ModelSpec):
        """Register a model"""
        self.models[model.id] = model
        logging.info(f"Registered model: {model.id} ({model.provider})")

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get model by ID"""
        return self.models.get(model_id)

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

    def _load_default_models(self):
        """Load default model configurations"""
        # OpenAI models
        gpt4 = ModelSpec(
            id="gpt-4",
            name="GPT-4",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling"],
            cost_per_1k_tokens={"input": 0.03, "output": 0.06},
            context_window=8192,
            max_output_tokens=4096,
        )
        self.register_model(gpt4)

        gpt4_turbo = ModelSpec(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling", "vision"],
            cost_per_1k_tokens={"input": 0.01, "output": 0.03},
            context_window=128000,
            max_output_tokens=4096,
        )
        self.register_model(gpt4_turbo)

        gpt35_turbo = ModelSpec(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            endpoint="https://api.openai.com/v1",
            capabilities=["chat", "function_calling"],
            cost_per_1k_tokens={"input": 0.0015, "output": 0.002},
            context_window=16384,
            max_output_tokens=4096,
        )
        self.register_model(gpt35_turbo)

        # Anthropic models
        claude3_opus = ModelSpec(
            id="claude-3-opus",
            name="Claude 3 Opus",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.015, "output": 0.075},
            context_window=200000,
            max_output_tokens=4096,
        )
        self.register_model(claude3_opus)

        claude3_sonnet = ModelSpec(
            id="claude-3-sonnet",
            name="Claude 3 Sonnet",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.003, "output": 0.015},
            context_window=200000,
            max_output_tokens=4096,
        )
        self.register_model(claude3_sonnet)

        claude3_haiku = ModelSpec(
            id="claude-3-haiku",
            name="Claude 3 Haiku",
            provider="anthropic",
            endpoint="https://api.anthropic.com/v1",
            capabilities=["chat", "vision"],
            cost_per_1k_tokens={"input": 0.00025, "output": 0.00125},
            context_window=200000,
            max_output_tokens=4096,
        )
        self.register_model(claude3_haiku)


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
