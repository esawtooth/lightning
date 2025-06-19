"""
Vextir OS Driver Framework - Standardized driver interface and registry
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union

from .event_bus import EventBus, get_event_bus
from .events import Event


class DriverType(Enum):
    AGENT = "agent"  # LLM-powered event processors
    TOOL = "tool"  # Specific capability providers
    IO = "io"  # External system interfaces
    UI = "ui"  # User interface handlers


@dataclass
class ResourceSpec:
    """Resource requirements for a driver"""

    memory_mb: int = 512
    timeout_seconds: int = 30
    max_concurrent: int = 10
    requires_gpu: bool = False
    environment_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class DriverManifest:
    """Driver registration manifest"""

    id: str
    name: str
    version: str
    author: str
    description: str
    driver_type: DriverType
    capabilities: List[str]
    resource_requirements: ResourceSpec
    dependencies: List[str] = field(default_factory=list)
    config_schema: Optional[Dict[str, Any]] = None
    enabled: bool = True


class Driver(ABC):
    """Base driver interface for Vextir OS"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        self.manifest = manifest
        self.config = config or {}
        self.event_bus = get_event_bus()
        self._initialized = False

    @abstractmethod
    async def handle_event(self, event: Event) -> List[Event]:
        """Process event and return new events"""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """List event types this driver handles"""
        pass

    @abstractmethod
    def get_resource_requirements(self) -> ResourceSpec:
        """Declare resource needs"""
        pass

    async def initialize(self):
        """Initialize driver (called once on startup)"""
        self._initialized = True
        logging.info(f"Driver {self.manifest.id} initialized")

    async def shutdown(self):
        """Cleanup driver resources"""
        logging.info(f"Driver {self.manifest.id} shutting down")

    def is_initialized(self) -> bool:
        """Check if driver is initialized"""
        return self._initialized


class AgentDriver(Driver):
    """Base class for LLM-powered agent drivers"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.model_name = config.get("model", "gpt-4o-mini") if config else "gpt-4o-mini"
        self.tools = config.get("tools", []) if config else []
        self.system_prompt = config.get("system_prompt", "") if config else ""
        self._completions_api = None

    async def get_model_client(self):
        """Get LLM client using the model registry"""
        if self._completions_api is None:
            from ..llm import get_completions_api
            self._completions_api = get_completions_api()
        return self._completions_api

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Make a completion request using the model registry"""
        api = await self.get_model_client()
        
        # Add system prompt if not already in messages
        if self.system_prompt and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": self.system_prompt}] + messages
        
        response = await api.create(
            model=self.model_name,
            messages=messages,
            user_id=self.manifest.id,  # Use driver ID for tracking
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.choices[0].message.content

    async def build_context(self, event: Event) -> str:
        """Build context for LLM from event and context hub"""
        # Default implementation - subclasses can override
        return f"Event: {event.type}\nData: {event.metadata}"


class ToolDriver(Driver):
    """Base class for tool capability drivers"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.api_endpoint = config.get("api_endpoint") if config else None
        self.api_key = config.get("api_key") if config else None


class IODriver(Driver):
    """Base class for external system interface drivers"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.connection_config = config.get("connection", {}) if config else {}


class UIDriver(Driver):
    """Base class for UI interface drivers"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.ui_apps: Dict[str, Any] = {}
        self.websockets: Dict[str, Any] = {}


@dataclass
class DriverInstance:
    """Running driver instance"""

    driver: Driver
    manifest: DriverManifest
    status: str = "stopped"  # stopped, starting, running, error
    error_message: Optional[str] = None
    last_activity: Optional[datetime] = None
    event_count: int = 0


class DriverRegistry:
    """Registry for managing drivers in Vextir OS"""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.manifests: Dict[str, DriverManifest] = {}
        self.driver_classes: Dict[str, Type[Driver]] = {}
        self.instances: Dict[str, DriverInstance] = {}
        self.capability_map: Dict[str, List[str]] = {}  # capability -> driver_ids

    async def register_driver(
        self,
        manifest: DriverManifest,
        driver_class: Type[Driver],
        config: Optional[Dict[str, Any]] = None,
    ):
        """Register a driver with the system"""
        if manifest.id in self.manifests:
            raise ValueError(f"Driver {manifest.id} already registered")

        # Validate manifest
        if not manifest.capabilities:
            raise ValueError(f"Driver {manifest.id} must declare capabilities")

        # Store manifest and class
        self.manifests[manifest.id] = manifest
        self.driver_classes[manifest.id] = driver_class

        # Update capability map
        for capability in manifest.capabilities:
            if capability not in self.capability_map:
                self.capability_map[capability] = []
            self.capability_map[capability].append(manifest.id)

        # Create instance if enabled
        if manifest.enabled:
            await self.start_driver(manifest.id, config)

        logging.info(f"Registered driver: {manifest.id} ({manifest.driver_type.value})")

    async def start_driver(
        self, driver_id: str, config: Optional[Dict[str, Any]] = None
    ):
        """Start a driver instance"""
        if driver_id not in self.manifests:
            raise ValueError(f"Driver {driver_id} not found")

        if driver_id in self.instances:
            raise ValueError(f"Driver {driver_id} already running")

        manifest = self.manifests[driver_id]
        driver_class = self.driver_classes[driver_id]

        try:
            # Create driver instance
            driver = driver_class(manifest, config)
            instance = DriverInstance(
                driver=driver, manifest=manifest, status="starting"
            )
            self.instances[driver_id] = instance

            # Initialize driver
            await driver.initialize()
            instance.status = "running"
            instance.last_activity = datetime.utcnow()

            logging.info(f"Started driver: {driver_id}")

        except Exception as e:
            if driver_id in self.instances:
                self.instances[driver_id].status = "error"
                self.instances[driver_id].error_message = str(e)
            logging.error(f"Failed to start driver {driver_id}: {e}")
            raise

    async def stop_driver(self, driver_id: str):
        """Stop a driver instance"""
        if driver_id not in self.instances:
            return

        instance = self.instances[driver_id]
        try:
            await instance.driver.shutdown()
        except Exception as e:
            logging.error(f"Error shutting down driver {driver_id}: {e}")

        del self.instances[driver_id]
        logging.info(f"Stopped driver: {driver_id}")

    async def route_event(self, event: Event) -> List[Event]:
        """Route event to capable drivers and collect results"""
        result_events = []

        # Find drivers that can handle this event type
        capable_drivers = self.capability_map.get(event.type, [])

        # Also check for wildcard capabilities
        for capability, driver_ids in self.capability_map.items():
            if capability.endswith(".*") and event.type.startswith(capability[:-1]):
                capable_drivers.extend(driver_ids)

        # Remove duplicates
        capable_drivers = list(set(capable_drivers))

        # Route to each capable driver
        for driver_id in capable_drivers:
            if driver_id not in self.instances:
                continue

            instance = self.instances[driver_id]
            if instance.status != "running":
                continue

            try:
                # Handle event
                events = await instance.driver.handle_event(event)
                result_events.extend(events)

                # Update instance stats
                instance.last_activity = datetime.utcnow()
                instance.event_count += 1

            except Exception as e:
                logging.error(
                    f"Error in driver {driver_id} handling event {event.type}: {e}"
                )
                instance.status = "error"
                instance.error_message = str(e)

        return result_events

    def get_drivers_by_capability(self, capability: str) -> List[str]:
        """Get driver IDs that provide a capability"""
        return self.capability_map.get(capability, [])

    def get_driver_status(self, driver_id: str) -> Optional[Dict[str, Any]]:
        """Get driver status information"""
        if driver_id not in self.instances:
            return None

        instance = self.instances[driver_id]
        return {
            "id": driver_id,
            "name": instance.manifest.name,
            "type": instance.manifest.driver_type.value,
            "status": instance.status,
            "error_message": instance.error_message,
            "last_activity": (
                instance.last_activity.isoformat() if instance.last_activity else None
            ),
            "event_count": instance.event_count,
            "capabilities": instance.manifest.capabilities,
        }

    def list_drivers(self) -> List[Dict[str, Any]]:
        """List all registered drivers"""
        drivers = []
        for driver_id, manifest in self.manifests.items():
            status_info = self.get_driver_status(driver_id) or {
                "id": driver_id,
                "name": manifest.name,
                "type": manifest.driver_type.value,
                "status": "stopped",
                "capabilities": manifest.capabilities,
            }
            drivers.append(status_info)
        return drivers


# Global driver registry
_global_registry: Optional[DriverRegistry] = None


def get_driver_registry() -> DriverRegistry:
    """Get global driver registry instance"""
    global _global_registry
    if _global_registry is None:
        event_bus = get_event_bus()
        _global_registry = DriverRegistry(event_bus)
    return _global_registry


# Decorator for easy driver registration
def driver(driver_id: str, driver_type: DriverType = DriverType.AGENT, **kwargs):
    """Decorator to register a driver class"""

    def decorator(cls: Type[Driver]):
        manifest = DriverManifest(
            id=driver_id,
            name=kwargs.get("name", driver_id),
            version=kwargs.get("version", "1.0.0"),
            author=kwargs.get("author", "unknown"),
            description=kwargs.get("description", ""),
            driver_type=driver_type,
            capabilities=kwargs.get("capabilities", []),
            resource_requirements=kwargs.get("resource_requirements", ResourceSpec()),
        )

        # Store for later registration
        cls._vextir_manifest = manifest
        return cls

    return decorator
