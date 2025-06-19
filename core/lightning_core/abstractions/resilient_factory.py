"""
Resilient factory for creating providers with health checks and circuit breakers.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Type, TypeVar, Callable
from functools import wraps

from .configuration import RuntimeConfig
from .container_runtime import ContainerRuntime
from .event_bus import EventBus
from .factory import ProviderFactory
from .health import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    HealthMonitor,
    HealthCheckable,
)
from .serverless import ServerlessRuntime
from .storage import StorageProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ResilientProviderWrapper:
    """Wraps a provider with circuit breaker functionality."""
    
    def __init__(self, provider: T, circuit_breaker: CircuitBreaker, name: str):
        self._provider = provider
        self._circuit_breaker = circuit_breaker
        self._name = name
        
    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the wrapped provider."""
        attr = getattr(self._provider, name)
        
        # If it's a coroutine function, wrap it with circuit breaker
        if asyncio.iscoroutinefunction(attr):
            @wraps(attr)
            async def wrapped(*args, **kwargs):
                try:
                    return await self._circuit_breaker.call(attr, *args, **kwargs)
                except CircuitBreakerOpenError:
                    logger.error(f"Circuit breaker open for {self._name}.{name}")
                    raise
                except Exception as e:
                    logger.error(f"Error in {self._name}.{name}: {e}")
                    raise
            return wrapped
        
        return attr
    
    @property
    def wrapped_provider(self) -> T:
        """Get the wrapped provider instance."""
        return self._provider
    
    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker instance."""
        return self._circuit_breaker


class ResilientProviderFactory(ProviderFactory):
    """
    Enhanced provider factory with health monitoring and circuit breakers.
    """
    
    def __init__(self, health_check_interval: int = 30):
        self._health_monitor = HealthMonitor(health_check_interval)
        self._circuit_configs: Dict[str, CircuitBreakerConfig] = {}
        self._fallback_providers: Dict[str, str] = {}
        self._wrapped_providers: Dict[str, ResilientProviderWrapper] = {}
        
    def set_circuit_config(self, provider_type: str, config: CircuitBreakerConfig):
        """Set circuit breaker configuration for a provider type."""
        self._circuit_configs[provider_type] = config
        
    def set_fallback_provider(self, primary: str, fallback: str):
        """Set a fallback provider for automatic failover."""
        self._fallback_providers[primary] = fallback
        
    async def start_health_monitoring(self):
        """Start the health monitoring service."""
        await self._health_monitor.start()
        
    async def stop_health_monitoring(self):
        """Stop the health monitoring service."""
        await self._health_monitor.stop()
    
    def _wrap_provider(self, provider: T, name: str, provider_type: str) -> T:
        """Wrap a provider with circuit breaker if it supports health checks."""
        # Check if provider supports health checks
        if isinstance(provider, HealthCheckable):
            # Get circuit config for this provider type
            circuit_config = self._circuit_configs.get(
                provider_type,
                CircuitBreakerConfig()  # Default config
            )
            
            # Create circuit breaker
            circuit_breaker = CircuitBreaker(circuit_config)
            
            # Register with health monitor
            self._health_monitor.register_provider(name, provider, circuit_config)
            
            # Create wrapped provider
            wrapped = ResilientProviderWrapper(provider, circuit_breaker, name)
            self._wrapped_providers[name] = wrapped
            
            logger.info(f"Wrapped provider '{name}' with circuit breaker")
            return wrapped  # Return the wrapper as the provider
        
        return provider
    
    @classmethod
    def create_storage_provider(
        cls, config: RuntimeConfig, **kwargs: Any
    ) -> StorageProvider:
        """Create a storage provider with resilience features."""
        # Create base provider
        provider = super().create_storage_provider(config, **kwargs)
        
        # If this is a resilient factory instance, wrap it
        if isinstance(cls, ResilientProviderFactory):
            instance = cls
            name = f"storage_{config.storage_provider}"
            provider = instance._wrap_provider(provider, name, "storage")
            
            # Handle fallback if configured
            if config.storage_provider in instance._fallback_providers:
                # TODO: Implement fallback logic
                pass
        
        return provider
    
    @classmethod
    def create_event_bus(
        cls, config: RuntimeConfig, **kwargs: Any
    ) -> EventBus:
        """Create an event bus with resilience features."""
        # Create base provider
        provider = super().create_event_bus(config, **kwargs)
        
        # If this is a resilient factory instance, wrap it
        if isinstance(cls, ResilientProviderFactory):
            instance = cls
            name = f"event_bus_{config.event_bus_provider}"
            provider = instance._wrap_provider(provider, name, "event_bus")
        
        return provider
    
    def get_provider_health(self, name: str) -> Dict[str, Any]:
        """Get health status of a specific provider."""
        return self._health_monitor.get_provider_status(name)
    
    def get_all_health(self) -> Dict[str, Any]:
        """Get health status of all providers."""
        return self._health_monitor.get_all_status()
    
    async def create_with_failover(
        self,
        primary_factory: Callable[[], T],
        fallback_factory: Optional[Callable[[], T]] = None,
        provider_name: str = "unknown"
    ) -> T:
        """
        Create a provider with automatic failover to fallback.
        
        Args:
            primary_factory: Function to create primary provider
            fallback_factory: Function to create fallback provider
            provider_name: Name for logging
            
        Returns:
            Provider instance (primary or fallback)
        """
        try:
            provider = primary_factory()
            logger.info(f"Created primary provider: {provider_name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to create primary provider {provider_name}: {e}")
            
            if fallback_factory:
                try:
                    provider = fallback_factory()
                    logger.warning(f"Using fallback provider for {provider_name}")
                    return provider
                except Exception as fallback_error:
                    logger.error(
                        f"Failed to create fallback provider {provider_name}: {fallback_error}"
                    )
                    raise
            raise


# Example usage function
async def create_resilient_runtime(config: RuntimeConfig) -> Dict[str, Any]:
    """
    Create a complete runtime with resilient providers.
    
    Returns dict with storage, event_bus, and factory instances.
    """
    # Create resilient factory
    factory = ResilientProviderFactory(health_check_interval=30)
    
    # Configure circuit breakers
    factory.set_circuit_config(
        "storage",
        CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=60
        )
    )
    
    factory.set_circuit_config(
        "event_bus", 
        CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30
        )
    )
    
    # Start health monitoring
    await factory.start_health_monitoring()
    
    # Create providers
    storage = factory.create_storage_provider(config)
    event_bus = factory.create_event_bus(config)
    
    return {
        "storage": storage,
        "event_bus": event_bus,
        "factory": factory,
    }