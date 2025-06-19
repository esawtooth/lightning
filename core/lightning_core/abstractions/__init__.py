"""
Lightning Core Abstractions

This module provides abstract base classes for core services,
enabling both local and cloud implementations.
"""

from .configuration import ConfigProvider, ExecutionMode, RuntimeConfig
from .container_runtime import Container, ContainerConfig, ContainerRuntime, ResourceRequirements
from .event_bus import (
    EventBus,
    EventHandler,
    EventMessage,
    DeduplicationConfig,
    ReplayConfig,
)
from .factory import ProviderFactory, get_provider_factory, set_provider_factory
from .health import (
    HealthCheckable,
    HealthCheckResult,
    HealthStatus,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    HealthMonitor,
)
from .serverless import FunctionConfig, FunctionHandler, ServerlessRuntime
from .storage import Document, DocumentStore, StorageProvider

__all__ = [
    # Storage
    "StorageProvider",
    "DocumentStore",
    "Document",
    # Event Bus
    "EventBus",
    "EventMessage",
    "EventHandler",
    "DeduplicationConfig",
    "ReplayConfig",
    # Container Runtime
    "ContainerRuntime",
    "Container",
    "ContainerConfig",
    "ResourceRequirements",
    # Serverless
    "ServerlessRuntime",
    "FunctionHandler",
    "FunctionConfig",
    # Configuration
    "ConfigProvider",
    "ExecutionMode",
    "RuntimeConfig",
    # Factory
    "ProviderFactory",
    "get_provider_factory",
    "set_provider_factory",
    # Health
    "HealthCheckable",
    "HealthCheckResult",
    "HealthStatus",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "HealthMonitor",
]
