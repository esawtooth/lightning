"""
Configuration abstraction layer for Lightning Core.

Provides configuration management for switching between
local and cloud execution modes.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
from enum import Enum
from dataclasses import dataclass, field
import os
import json


class ExecutionMode(Enum):
    """Execution mode enumeration."""
    LOCAL = "local"
    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    HYBRID = "hybrid"  # Local with some cloud services


@dataclass
class RuntimeConfig:
    """Runtime configuration for Lightning Core."""
    mode: ExecutionMode = ExecutionMode.LOCAL
    
    # Storage configuration
    storage_provider: str = "local"  # local, azure_cosmos, dynamodb, firestore
    storage_connection_string: Optional[str] = None
    storage_endpoint: Optional[str] = None
    storage_path: Optional[str] = "./data"  # For local storage
    
    # Event bus configuration
    event_bus_provider: str = "local"  # local, azure_service_bus, sqs, pubsub
    event_bus_connection_string: Optional[str] = None
    event_bus_endpoint: Optional[str] = None
    
    # Container runtime configuration
    container_runtime: str = "docker"  # docker, azure_aci, ecs, cloud_run
    container_registry: Optional[str] = None
    container_registry_username: Optional[str] = None
    container_registry_password: Optional[str] = None
    
    # Serverless configuration
    serverless_provider: str = "local"  # local, azure_functions, lambda, cloud_functions
    serverless_endpoint: Optional[str] = None
    
    # General configuration
    region: Optional[str] = None
    project_id: Optional[str] = None
    resource_group: Optional[str] = None
    
    # Security configuration
    auth_enabled: bool = True
    encryption_enabled: bool = True
    api_keys: Dict[str, str] = field(default_factory=dict)
    
    # Logging configuration
    log_level: str = "INFO"
    log_provider: str = "local"  # local, application_insights, cloudwatch, stackdriver
    log_connection_string: Optional[str] = None
    
    # Performance configuration
    max_concurrent_operations: int = 100
    operation_timeout_seconds: int = 300
    retry_max_attempts: int = 3
    retry_backoff_seconds: int = 1
    
    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        """Create configuration from environment variables."""
        config = cls()
        
        # Mode
        mode_str = os.getenv("LIGHTNING_MODE", "local").lower()
        config.mode = ExecutionMode(mode_str)
        
        # Storage
        config.storage_provider = os.getenv("LIGHTNING_STORAGE_PROVIDER", "local")
        config.storage_connection_string = os.getenv("LIGHTNING_STORAGE_CONNECTION")
        config.storage_endpoint = os.getenv("LIGHTNING_STORAGE_ENDPOINT")
        config.storage_path = os.getenv("LIGHTNING_STORAGE_PATH", "./data")
        
        # Event bus
        config.event_bus_provider = os.getenv("LIGHTNING_EVENT_BUS_PROVIDER", "local")
        config.event_bus_connection_string = os.getenv("LIGHTNING_EVENT_BUS_CONNECTION")
        config.event_bus_endpoint = os.getenv("LIGHTNING_EVENT_BUS_ENDPOINT")
        
        # Container runtime
        config.container_runtime = os.getenv("LIGHTNING_CONTAINER_RUNTIME", "docker")
        config.container_registry = os.getenv("LIGHTNING_CONTAINER_REGISTRY")
        config.container_registry_username = os.getenv("LIGHTNING_CONTAINER_REGISTRY_USERNAME")
        config.container_registry_password = os.getenv("LIGHTNING_CONTAINER_REGISTRY_PASSWORD")
        
        # Serverless
        config.serverless_provider = os.getenv("LIGHTNING_SERVERLESS_PROVIDER", "local")
        config.serverless_endpoint = os.getenv("LIGHTNING_SERVERLESS_ENDPOINT")
        
        # General
        config.region = os.getenv("LIGHTNING_REGION")
        config.project_id = os.getenv("LIGHTNING_PROJECT_ID")
        config.resource_group = os.getenv("LIGHTNING_RESOURCE_GROUP")
        
        # Security
        config.auth_enabled = os.getenv("LIGHTNING_AUTH_ENABLED", "true").lower() == "true"
        config.encryption_enabled = os.getenv("LIGHTNING_ENCRYPTION_ENABLED", "true").lower() == "true"
        
        # API keys
        for key, value in os.environ.items():
            if key.startswith("LIGHTNING_API_KEY_"):
                api_name = key.replace("LIGHTNING_API_KEY_", "").lower()
                config.api_keys[api_name] = value
        
        # Logging
        config.log_level = os.getenv("LIGHTNING_LOG_LEVEL", "INFO")
        config.log_provider = os.getenv("LIGHTNING_LOG_PROVIDER", "local")
        config.log_connection_string = os.getenv("LIGHTNING_LOG_CONNECTION")
        
        # Performance
        if max_concurrent := os.getenv("LIGHTNING_MAX_CONCURRENT_OPERATIONS"):
            config.max_concurrent_operations = int(max_concurrent)
        if timeout := os.getenv("LIGHTNING_OPERATION_TIMEOUT"):
            config.operation_timeout_seconds = int(timeout)
        if retry_attempts := os.getenv("LIGHTNING_RETRY_MAX_ATTEMPTS"):
            config.retry_max_attempts = int(retry_attempts)
        if retry_backoff := os.getenv("LIGHTNING_RETRY_BACKOFF"):
            config.retry_backoff_seconds = int(retry_backoff)
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "mode": self.mode.value,
            "storage_provider": self.storage_provider,
            "storage_connection_string": self.storage_connection_string,
            "storage_endpoint": self.storage_endpoint,
            "storage_path": self.storage_path,
            "event_bus_provider": self.event_bus_provider,
            "event_bus_connection_string": self.event_bus_connection_string,
            "event_bus_endpoint": self.event_bus_endpoint,
            "container_runtime": self.container_runtime,
            "container_registry": self.container_registry,
            "serverless_provider": self.serverless_provider,
            "serverless_endpoint": self.serverless_endpoint,
            "region": self.region,
            "project_id": self.project_id,
            "resource_group": self.resource_group,
            "auth_enabled": self.auth_enabled,
            "encryption_enabled": self.encryption_enabled,
            "log_level": self.log_level,
            "log_provider": self.log_provider,
            "log_connection_string": self.log_connection_string,
            "max_concurrent_operations": self.max_concurrent_operations,
            "operation_timeout_seconds": self.operation_timeout_seconds,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        """Create configuration from dictionary."""
        config = cls()
        
        if "mode" in data:
            config.mode = ExecutionMode(data["mode"])
        
        # Copy all other fields
        for key, value in data.items():
            if hasattr(config, key) and key != "mode":
                setattr(config, key, value)
        
        return config
    
    def save(self, path: str) -> None:
        """Save configuration to file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> "RuntimeConfig":
        """Load configuration from file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


T = TypeVar("T")


class ConfigProvider(ABC):
    """Abstract base class for configuration providers."""
    
    @abstractmethod
    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Get a configuration value."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        pass
    
    @abstractmethod
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get all configuration values in a section."""
        pass
    
    @abstractmethod
    def reload(self) -> None:
        """Reload configuration from source."""
        pass