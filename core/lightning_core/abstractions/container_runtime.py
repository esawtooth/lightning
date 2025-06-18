"""
Container runtime abstraction layer for Lightning Core.

Provides abstract base classes for container orchestration,
supporting both cloud (e.g., Azure Container Instances) and local (Docker) implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid


class ContainerState(Enum):
    """Container state enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    TERMINATED = "terminated"


class ResourceRequirements:
    """Container resource requirements."""
    
    def __init__(
        self,
        cpu: float = 1.0,
        memory_gb: float = 1.5,
        gpu_count: int = 0,
        gpu_sku: Optional[str] = None
    ):
        self.cpu = cpu
        self.memory_gb = memory_gb
        self.gpu_count = gpu_count
        self.gpu_sku = gpu_sku


class Port:
    """Container port configuration."""
    
    def __init__(
        self,
        port: int,
        protocol: str = "TCP",
        name: Optional[str] = None
    ):
        self.port = port
        self.protocol = protocol
        self.name = name or f"port-{port}"


@dataclass
class ContainerConfig:
    """Container configuration."""
    name: str
    image: str
    command: Optional[List[str]] = None
    args: Optional[List[str]] = None
    environment_variables: Dict[str, str] = field(default_factory=dict)
    ports: List[Port] = field(default_factory=list)
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    volumes: Dict[str, str] = field(default_factory=dict)  # {host_path: container_path}
    working_dir: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    restart_policy: str = "OnFailure"  # Always, OnFailure, Never
    network_mode: Optional[str] = None
    dns_servers: List[str] = field(default_factory=list)
    
    def add_port(self, port: int, protocol: str = "TCP", name: Optional[str] = None) -> None:
        """Add a port to the container configuration."""
        self.ports.append(Port(port, protocol, name))
    
    def add_environment_variable(self, key: str, value: str) -> None:
        """Add an environment variable."""
        self.environment_variables[key] = value
    
    def add_volume(self, host_path: str, container_path: str) -> None:
        """Add a volume mount."""
        self.volumes[host_path] = container_path


@dataclass
class Container:
    """Container instance information."""
    id: str
    name: str
    state: ContainerState
    config: ContainerConfig
    ip_address: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    logs: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContainerRuntime(ABC):
    """Abstract base class for container runtime implementations."""
    
    @abstractmethod
    async def create_container(
        self,
        config: ContainerConfig,
        wait_for_ready: bool = True
    ) -> Container:
        """Create and start a new container."""
        pass
    
    @abstractmethod
    async def get_container(self, container_id: str) -> Optional[Container]:
        """Get container information by ID."""
        pass
    
    @abstractmethod
    async def list_containers(
        self,
        labels: Optional[Dict[str, str]] = None,
        state: Optional[ContainerState] = None
    ) -> List[Container]:
        """List containers with optional filtering."""
        pass
    
    @abstractmethod
    async def stop_container(
        self,
        container_id: str,
        timeout_seconds: int = 30
    ) -> None:
        """Stop a running container."""
        pass
    
    @abstractmethod
    async def remove_container(
        self,
        container_id: str,
        force: bool = False
    ) -> None:
        """Remove a container."""
        pass
    
    @abstractmethod
    async def get_container_logs(
        self,
        container_id: str,
        tail: Optional[int] = None,
        since: Optional[str] = None,
        follow: bool = False
    ) -> str:
        """Get container logs."""
        pass
    
    @abstractmethod
    async def exec_command(
        self,
        container_id: str,
        command: List[str],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None
    ) -> tuple[int, str, str]:
        """
        Execute a command inside a running container.
        Returns (exit_code, stdout, stderr).
        """
        pass
    
    @abstractmethod
    async def pull_image(
        self,
        image: str,
        auth_config: Optional[Dict[str, str]] = None
    ) -> None:
        """Pull a container image."""
        pass
    
    @abstractmethod
    async def push_image(
        self,
        image: str,
        auth_config: Optional[Dict[str, str]] = None
    ) -> None:
        """Push a container image to registry."""
        pass
    
    @abstractmethod
    async def build_image(
        self,
        context_path: str,
        dockerfile: str = "Dockerfile",
        tag: str = None,
        build_args: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build a container image.
        Returns the image ID.
        """
        pass
    
    @abstractmethod
    async def wait_for_container(
        self,
        container_id: str,
        timeout_seconds: Optional[int] = None
    ) -> int:
        """
        Wait for a container to finish.
        Returns the exit code.
        """
        pass
    
    @abstractmethod
    async def get_container_stats(
        self,
        container_id: str
    ) -> Dict[str, Any]:
        """Get container resource usage statistics."""
        pass