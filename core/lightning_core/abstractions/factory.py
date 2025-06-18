"""
Factory for creating abstraction implementations based on configuration.
"""

import importlib
from typing import Any, Dict, Optional, Type

from .configuration import ExecutionMode, RuntimeConfig
from .container_runtime import ContainerRuntime
from .event_bus import EventBus
from .serverless import ServerlessRuntime
from .storage import StorageProvider


class ProviderFactory:
    """Factory for creating provider implementations."""

    # Provider mappings
    _storage_providers: Dict[str, str] = {
        "local": "lightning_core.providers.local.storage.LocalStorageProvider",
        "azure_cosmos": "lightning_core.providers.azure.storage.CosmosStorageProvider",
        "dynamodb": "lightning_core.providers.aws.storage.DynamoDBStorageProvider",
        "firestore": "lightning_core.providers.gcp.storage.FirestoreStorageProvider",
    }

    _event_bus_providers: Dict[str, str] = {
        "local": "lightning_core.providers.local.event_bus.LocalEventBus",
        "redis": "lightning_core.providers.redis.event_bus.RedisEventBus",
        "azure_service_bus": "lightning_core.providers.azure.event_bus.ServiceBusEventBus",
        "sqs": "lightning_core.providers.aws.event_bus.SQSEventBus",
        "pubsub": "lightning_core.providers.gcp.event_bus.PubSubEventBus",
    }

    _container_runtime_providers: Dict[str, str] = {
        "docker": "lightning_core.providers.local.container_runtime.DockerContainerRuntime",
        "azure_aci": "lightning_core.providers.azure.container_runtime.ACIContainerRuntime",
        "ecs": "lightning_core.providers.aws.container_runtime.ECSContainerRuntime",
        "cloud_run": "lightning_core.providers.gcp.container_runtime.CloudRunContainerRuntime",
    }

    _serverless_providers: Dict[str, str] = {
        "local": "lightning_core.providers.local.serverless.LocalServerlessRuntime",
        "azure_functions": "lightning_core.providers.azure.serverless.AzureFunctionsRuntime",
        "lambda": "lightning_core.providers.aws.serverless.LambdaRuntime",
        "cloud_functions": "lightning_core.providers.gcp.serverless.CloudFunctionsRuntime",
    }

    @classmethod
    def _load_class(cls, module_path: str) -> Type:
        """Dynamically load a class from module path."""
        module_name, class_name = module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    @classmethod
    def create_storage_provider(
        cls, config: RuntimeConfig, **kwargs: Any
    ) -> StorageProvider:
        """Create a storage provider based on configuration."""
        provider_path = cls._storage_providers.get(config.storage_provider)
        if not provider_path:
            raise ValueError(f"Unknown storage provider: {config.storage_provider}")

        provider_class = cls._load_class(provider_path)

        # Prepare provider-specific configuration
        provider_config = {
            "connection_string": config.storage_connection_string,
            "endpoint": config.storage_endpoint,
            "path": config.storage_path,
            **kwargs,
        }

        return provider_class(**provider_config)

    @classmethod
    def create_event_bus(cls, config: RuntimeConfig, **kwargs: Any) -> EventBus:
        """Create an event bus based on configuration."""
        provider_path = cls._event_bus_providers.get(config.event_bus_provider)
        if not provider_path:
            raise ValueError(f"Unknown event bus provider: {config.event_bus_provider}")

        provider_class = cls._load_class(provider_path)

        # Prepare provider-specific configuration
        provider_config = {
            "connection_string": config.event_bus_connection_string,
            "endpoint": config.event_bus_endpoint,
            **kwargs,
        }

        return provider_class(**provider_config)

    @classmethod
    def create_container_runtime(
        cls, config: RuntimeConfig, **kwargs: Any
    ) -> ContainerRuntime:
        """Create a container runtime based on configuration."""
        provider_path = cls._container_runtime_providers.get(config.container_runtime)
        if not provider_path:
            raise ValueError(f"Unknown container runtime: {config.container_runtime}")

        provider_class = cls._load_class(provider_path)

        # Prepare provider-specific configuration
        provider_config = {
            "registry": config.container_registry,
            "registry_username": config.container_registry_username,
            "registry_password": config.container_registry_password,
            "region": config.region,
            "resource_group": config.resource_group,
            **kwargs,
        }

        return provider_class(**provider_config)

    @classmethod
    def create_serverless_runtime(
        cls, config: RuntimeConfig, **kwargs: Any
    ) -> ServerlessRuntime:
        """Create a serverless runtime based on configuration."""
        provider_path = cls._serverless_providers.get(config.serverless_provider)
        if not provider_path:
            raise ValueError(
                f"Unknown serverless provider: {config.serverless_provider}"
            )

        provider_class = cls._load_class(provider_path)

        # Prepare provider-specific configuration
        provider_config = {
            "endpoint": config.serverless_endpoint,
            "region": config.region,
            "project_id": config.project_id,
            "resource_group": config.resource_group,
            **kwargs,
        }

        return provider_class(**provider_config)

    @classmethod
    def register_storage_provider(cls, name: str, module_path: str) -> None:
        """Register a custom storage provider."""
        cls._storage_providers[name] = module_path

    @classmethod
    def register_event_bus_provider(cls, name: str, module_path: str) -> None:
        """Register a custom event bus provider."""
        cls._event_bus_providers[name] = module_path

    @classmethod
    def register_container_runtime_provider(cls, name: str, module_path: str) -> None:
        """Register a custom container runtime provider."""
        cls._container_runtime_providers[name] = module_path

    @classmethod
    def register_serverless_provider(cls, name: str, module_path: str) -> None:
        """Register a custom serverless provider."""
        cls._serverless_providers[name] = module_path


# Global factory instance
_global_factory: Optional[ProviderFactory] = None
_global_config: Optional[RuntimeConfig] = None


def get_provider_factory() -> ProviderFactory:
    """Get the global provider factory instance."""
    global _global_factory, _global_config
    
    if _global_factory is None:
        _global_factory = ProviderFactory()
        
    if _global_config is None:
        # Create default local configuration for testing
        _global_config = RuntimeConfig(
            execution_mode=ExecutionMode.LOCAL,
            storage_provider="local",
            event_bus_provider="local",
            container_runtime="docker",
            serverless_provider="local"
        )
    
    return _global_factory


def set_provider_factory(factory: ProviderFactory, config: RuntimeConfig) -> None:
    """Set the global provider factory instance."""
    global _global_factory, _global_config
    _global_factory = factory
    _global_config = config


def get_runtime_config() -> RuntimeConfig:
    """Get the global runtime configuration."""
    get_provider_factory()  # Ensure config is initialized
    return _global_config
