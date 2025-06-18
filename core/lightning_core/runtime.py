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
)

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

    def __init__(self, config: Optional[RuntimeConfig] = None):
        """
        Initialize the Lightning runtime.

        Args:
            config: Runtime configuration. If not provided, will load from environment.
        """
        self.config = config or RuntimeConfig.from_env()

        # Provider instances
        self._storage: Optional[StorageProvider] = None
        self._event_bus: Optional[EventBus] = None
        self._container_runtime: Optional[ContainerRuntime] = None
        self._serverless_runtime: Optional[ServerlessRuntime] = None

        # Track initialization state
        self._initialized = False

        logger.info(f"Lightning Runtime initialized in {self.config.mode.value} mode")

    @property
    def storage(self) -> StorageProvider:
        """Get the storage provider instance."""
        if not self._storage:
            self._storage = ProviderFactory.create_storage_provider(self.config)
        return self._storage

    @property
    def event_bus(self) -> EventBus:
        """Get the event bus instance."""
        if not self._event_bus:
            self._event_bus = ProviderFactory.create_event_bus(self.config)
        return self._event_bus

    @property
    def container_runtime(self) -> ContainerRuntime:
        """Get the container runtime instance."""
        if not self._container_runtime:
            self._container_runtime = ProviderFactory.create_container_runtime(
                self.config
            )
        return self._container_runtime

    @property
    def serverless(self) -> ServerlessRuntime:
        """Get the serverless runtime instance."""
        if not self._serverless_runtime:
            self._serverless_runtime = ProviderFactory.create_serverless_runtime(
                self.config
            )
        return self._serverless_runtime

    async def initialize(self) -> None:
        """Initialize all services."""
        if self._initialized:
            return

        logger.info("Initializing Lightning Runtime services...")

        # Initialize storage
        if self._storage:
            await self._storage.initialize()

        # Start event bus
        if self._event_bus:
            await self._event_bus.start()

        self._initialized = True
        logger.info("Lightning Runtime services initialized")

    async def shutdown(self) -> None:
        """Shutdown all services."""
        logger.info("Shutting down Lightning Runtime services...")

        # Stop event bus
        if self._event_bus:
            await self._event_bus.stop()

        # Close storage
        if self._storage:
            await self._storage.close()

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
