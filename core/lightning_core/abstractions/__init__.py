"""
Lightning Core Abstractions

This module provides abstract base classes for core services,
enabling both local and cloud implementations.
"""

from .storage import StorageProvider, DocumentStore, Document
from .event_bus import EventBus, EventMessage, EventHandler
from .container_runtime import ContainerRuntime, Container, ContainerConfig
from .serverless import ServerlessRuntime, FunctionHandler, FunctionConfig
from .configuration import ConfigProvider, ExecutionMode

__all__ = [
    # Storage
    "StorageProvider",
    "DocumentStore",
    "Document",
    
    # Event Bus
    "EventBus",
    "EventMessage",
    "EventHandler",
    
    # Container Runtime
    "ContainerRuntime",
    "Container",
    "ContainerConfig",
    
    # Serverless
    "ServerlessRuntime",
    "FunctionHandler",
    "FunctionConfig",
    
    # Configuration
    "ConfigProvider",
    "ExecutionMode",
]