"""
Lightning Core runtime that manages all providers and services.

This is the main entry point for using Lightning Core with
abstracted providers.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Type, TypeVar

from .abstractions import (
    ContainerRuntime,
    Document,
    EventBus,
    EventHandler,
    EventMessage,
    ExecutionMode,
    ProviderFactory,
    RuntimeConfig,
    ServerlessRuntime,
    StorageProvider,
    CircuitBreakerConfig,
)
from .abstractions.resilient_factory import ResilientProviderFactory
from .mcp import (
    MCPRegistry,
    MCPSandbox,
    MCPSecurityProxy,
    MCPDriver,
)
from .mcp.config import MCPConfigLoader
from .vextir_os.security import SecurityManager

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=Document)


class LightningRuntime:
    """
    Main runtime class that manages all Lightning Core services.

    This class provides a unified interface for:
    - Storage operations
    - Event processing
    - Container management
    - Serverless function execution
    """

    def __init__(self, config: Optional[RuntimeConfig] = None, use_resilient_providers: bool = True):
        """
        Initialize the Lightning runtime.

        Args:
            config: Runtime configuration. If not provided, will load from environment.
            use_resilient_providers: Whether to use resilient providers with health checks
        """
        self.config = config or RuntimeConfig.from_env()
        self.use_resilient_providers = use_resilient_providers

        # Provider factory
        if use_resilient_providers:
            self._factory = ResilientProviderFactory()
            self._setup_resilient_factory()
        else:
            self._factory = ProviderFactory

        # Provider instances
        self._storage: Optional[StorageProvider] = None
        self._event_bus: Optional[EventBus] = None
        self._container_runtime: Optional[ContainerRuntime] = None
        self._serverless_runtime: Optional[ServerlessRuntime] = None

        # MCP components
        self._mcp_registry: Optional[MCPRegistry] = None
        self._mcp_sandbox: Optional[MCPSandbox] = None
        self._mcp_security_proxy: Optional[MCPSecurityProxy] = None
        self._mcp_driver: Optional[MCPDriver] = None
        self._security_manager: Optional[SecurityManager] = None

        # Tool registry
        self._tool_registry = None

        # Track initialization state
        self._initialized = False
        self._mcp_initialized = False
        self._tools_initialized = False

        logger.info(f"Lightning Runtime initialized in {self.config.mode.value} mode")

    def _setup_resilient_factory(self):
        """Configure the resilient factory with circuit breakers."""
        # Configure storage circuit breaker
        self._factory.set_circuit_config(
            "storage",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=60
            )
        )
        
        # Configure event bus circuit breaker
        self._factory.set_circuit_config(
            "event_bus",
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=30
            )
        )
        
        # Configure container runtime circuit breaker
        self._factory.set_circuit_config(
            "container",
            CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=1,
                timeout_seconds=120
            )
        )

    @property
    def storage(self) -> StorageProvider:
        """Get the storage provider instance."""
        if not self._storage:
            self._storage = self._factory.create_storage_provider(self.config)
        return self._storage

    @property
    def event_bus(self) -> EventBus:
        """Get the event bus instance."""
        if not self._event_bus:
            self._event_bus = self._factory.create_event_bus(self.config)
        return self._event_bus

    @property
    def container_runtime(self) -> ContainerRuntime:
        """Get the container runtime instance."""
        if not self._container_runtime:
            self._container_runtime = self._factory.create_container_runtime(
                self.config
            )
        return self._container_runtime

    @property
    def serverless(self) -> ServerlessRuntime:
        """Get the serverless runtime instance."""
        if not self._serverless_runtime:
            self._serverless_runtime = self._factory.create_serverless_runtime(
                self.config
            )
        return self._serverless_runtime

    @property
    def mcp_registry(self) -> MCPRegistry:
        """Get the MCP registry instance."""
        if not self._mcp_registry:
            self._mcp_registry = MCPRegistry(self.storage)
        return self._mcp_registry

    @property
    def mcp_sandbox(self) -> MCPSandbox:
        """Get the MCP sandbox instance."""
        if not self._mcp_sandbox:
            self._mcp_sandbox = MCPSandbox()
        return self._mcp_sandbox

    @property
    def mcp_security_proxy(self) -> MCPSecurityProxy:
        """Get the MCP security proxy instance."""
        if not self._mcp_security_proxy:
            if not self._security_manager:
                from .vextir_os.security import SecurityManager
                self._security_manager = SecurityManager()
            self._mcp_security_proxy = MCPSecurityProxy(self._security_manager)
        return self._mcp_security_proxy

    @property
    def mcp_driver(self) -> MCPDriver:
        """Get the MCP driver instance."""
        if not self._mcp_driver:
            self._mcp_driver = MCPDriver(
                self.mcp_registry,
                self.mcp_security_proxy,
                self.mcp_sandbox
            )
        return self._mcp_driver

    @property
    def tool_registry(self):
        """Get the simplified tool registry instance."""
        if not self._tool_registry:
            from .tools import get_tool_registry
            self._tool_registry = get_tool_registry()
        return self._tool_registry

    async def initialize(self) -> None:
        """Initialize all services."""
        if self._initialized:
            return

        logger.info("Initializing Lightning Runtime services...")

        # Start health monitoring if using resilient providers
        if self.use_resilient_providers and isinstance(self._factory, ResilientProviderFactory):
            await self._factory.start_health_monitoring()
            logger.info("Started health monitoring for providers")

        # Initialize storage
        if self._storage:
            await self._storage.initialize()

        # Start event bus
        if self._event_bus:
            await self._event_bus.start()

        self._initialized = True
        logger.info("Lightning Runtime services initialized")

    async def initialize_mcp(self, load_config: bool = True) -> None:
        """Initialize MCP services."""
        if self._mcp_initialized:
            return

        logger.info("Initializing MCP services...")

        # Initialize MCP registry
        await self.mcp_registry.initialize()

        # Load configuration if requested
        if load_config:
            config_loader = MCPConfigLoader()
            configs = config_loader.load_server_configs()
            
            for config in configs:
                try:
                    await self.mcp_registry.register_server(config)
                    logger.info(f"Registered MCP server from config: {config.id}")
                except Exception as e:
                    logger.error(f"Failed to register MCP server {config.id}: {e}")

        # Initialize MCP driver
        await self.mcp_driver.initialize()

        self._mcp_initialized = True
        logger.info("MCP services initialized")

    async def initialize_tools(self) -> None:
        """Initialize the tool registry with all providers."""
        if self._tools_initialized:
            return

        logger.info("Initializing tool registry...")

        # Initialize with MCP registry if available
        from .tools import initialize_tool_registry
        self._tool_registry = await initialize_tool_registry(
            mcp_registry=self._mcp_registry if self._mcp_initialized else None
        )

        self._tools_initialized = True
        logger.info("Tool registry initialized")

    async def shutdown(self) -> None:
        """Shutdown all services."""
        logger.info("Shutting down Lightning Runtime services...")

        # Shutdown MCP services
        if self._mcp_initialized:
            if self._mcp_driver:
                await self._mcp_driver.shutdown()
            if self._mcp_sandbox:
                await self._mcp_sandbox.cleanup_all()
            self._mcp_initialized = False

        # Stop event bus
        if self._event_bus:
            await self._event_bus.stop()

        # Close storage
        if self._storage:
            await self._storage.close()

        # Stop health monitoring if using resilient providers
        if self.use_resilient_providers and isinstance(self._factory, ResilientProviderFactory):
            await self._factory.stop_health_monitoring()
            logger.info("Stopped health monitoring")

        self._initialized = False
        logger.info("Lightning Runtime services shut down")

    @asynccontextmanager
    async def session(self):
        """Context manager for runtime session."""
        await self.initialize()
        try:
            yield self
        finally:
            await self.shutdown()

    # Convenience methods for common operations

    def get_document_store(self, container: str, document_type: Type[T]):
        """Get a document store for a specific container."""
        return self.storage.get_document_store(container, document_type)

    async def publish_event(
        self, event: EventMessage, topic: Optional[str] = None
    ) -> None:
        """Publish an event to the event bus."""
        await self.event_bus.publish(event, topic)

    async def subscribe_to_events(
        self, event_type: str, handler: EventHandler, topic: Optional[str] = None
    ) -> str:
        """Subscribe to events of a specific type."""
        return await self.event_bus.subscribe(event_type, handler, topic)

    def is_local_mode(self) -> bool:
        """Check if running in local mode."""
        return self.config.mode == ExecutionMode.LOCAL

    def is_cloud_mode(self) -> bool:
        """Check if running in cloud mode."""
        return self.config.mode in [
            ExecutionMode.AZURE,
            ExecutionMode.AWS,
            ExecutionMode.GCP,
        ]
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all providers."""
        if not self.use_resilient_providers or not isinstance(self._factory, ResilientProviderFactory):
            return {"status": "health monitoring not enabled"}
        
        return self._factory.get_all_health()
    
    async def check_provider_health(self, provider_name: str) -> Dict[str, Any]:
        """Check health of a specific provider."""
        if not self.use_resilient_providers or not isinstance(self._factory, ResilientProviderFactory):
            return {"status": "health monitoring not enabled"}
        
        return self._factory.get_provider_health(provider_name)


# Global runtime instance
_runtime: Optional[LightningRuntime] = None


def get_runtime(config: Optional[RuntimeConfig] = None) -> LightningRuntime:
    """
    Get the global Lightning runtime instance.

    Args:
        config: Runtime configuration. Only used on first call.

    Returns:
        The global Lightning runtime instance.
    """
    global _runtime
    if _runtime is None:
        _runtime = LightningRuntime(config)
    return _runtime


async def initialize_runtime(
    config: Optional[RuntimeConfig] = None,
) -> LightningRuntime:
    """
    Initialize and return the global Lightning runtime.

    Args:
        config: Runtime configuration. Only used on first call.

    Returns:
        The initialized Lightning runtime instance.
    """
    runtime = get_runtime(config)
    await runtime.initialize()
    return runtime
