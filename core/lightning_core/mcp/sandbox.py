"""Sandboxing mechanisms for MCP server execution."""

import asyncio
import os
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class NetworkPolicy(str, Enum):
    """Network access policies for sandboxed environments."""
    ALLOW_ALL = "allow_all"
    DENY_ALL = "deny_all"
    RESTRICTED = "restricted"


class FilesystemPolicy(str, Enum):
    """Filesystem access policies."""
    ALLOW_ALL = "allow_all"
    DENY_ALL = "deny_all"
    RESTRICTED = "restricted"


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed execution."""
    max_cpu_percent: int = 50
    max_memory_mb: int = 512
    max_execution_time_seconds: int = 300
    max_file_size_mb: int = 100
    max_open_files: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceLimits":
        return cls(**data)


@dataclass
class NetworkConfig:
    """Network configuration for sandboxed environments."""
    policy: NetworkPolicy = NetworkPolicy.DENY_ALL
    allowed_domains: List[str] = field(default_factory=list)
    allowed_ports: List[int] = field(default_factory=lambda: [80, 443])
    dns_servers: List[str] = field(default_factory=lambda: ["8.8.8.8", "8.8.4.4"])
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["policy"] = self.policy.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NetworkConfig":
        data = data.copy()
        data["policy"] = NetworkPolicy(data["policy"])
        return cls(**data)


@dataclass
class FilesystemConfig:
    """Filesystem configuration for sandboxed environments."""
    policy: FilesystemPolicy = FilesystemPolicy.RESTRICTED
    allowed_paths: List[str] = field(default_factory=list)
    read_only_paths: List[str] = field(default_factory=list)
    temp_dir: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["policy"] = self.policy.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilesystemConfig":
        data = data.copy()
        data["policy"] = FilesystemPolicy(data["policy"])
        return cls(**data)


@dataclass
class SandboxConfig:
    """Complete sandbox configuration."""
    enabled: bool = True
    use_containers: bool = True
    container_image: str = "lightning-mcp-sandbox:latest"
    network_config: NetworkConfig = field(default_factory=NetworkConfig)
    filesystem_config: FilesystemConfig = field(default_factory=FilesystemConfig)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    allowed_capabilities: List[str] = field(default_factory=list)
    environment_vars: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "use_containers": self.use_containers,
            "container_image": self.container_image,
            "network_config": self.network_config.to_dict(),
            "filesystem_config": self.filesystem_config.to_dict(),
            "resource_limits": self.resource_limits.to_dict(),
            "allowed_capabilities": self.allowed_capabilities,
            "environment_vars": self.environment_vars,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxConfig":
        data = data.copy()
        data["network_config"] = NetworkConfig.from_dict(data["network_config"])
        data["filesystem_config"] = FilesystemConfig.from_dict(data["filesystem_config"])
        data["resource_limits"] = ResourceLimits.from_dict(data["resource_limits"])
        return cls(**data)


class IsolatedEnvironment:
    """Represents an isolated execution environment."""
    
    def __init__(self, 
                 server_id: str,
                 sandbox_config: SandboxConfig):
        self.server_id = server_id
        self.sandbox_config = sandbox_config
        self.container_id: Optional[str] = None
        self.temp_dir: Optional[str] = None
        
    async def setup(self) -> None:
        """Set up the isolated environment."""
        if not self.sandbox_config.enabled:
            logger.info(f"Sandbox disabled for server {self.server_id}")
            return
        
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix=f"mcp_{self.server_id}_")
        
        if self.sandbox_config.use_containers:
            await self._setup_container()
        else:
            await self._setup_process_isolation()
    
    async def cleanup(self) -> None:
        """Clean up the isolated environment."""
        if self.container_id:
            await self._cleanup_container()
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    async def _setup_container(self) -> None:
        """Set up Docker container for isolation."""
        # Import here to avoid dependency if not using containers
        try:
            import docker
            from docker.types import Mount
        except ImportError:
            logger.warning("Docker not available, falling back to process isolation")
            await self._setup_process_isolation()
            return
        
        client = docker.from_env()
        
        # Prepare mounts
        mounts = []
        fs_config = self.sandbox_config.filesystem_config
        
        # Add allowed paths as read-write mounts
        for path in fs_config.allowed_paths:
            if os.path.exists(path):
                mounts.append(Mount(
                    target=path,
                    source=path,
                    type="bind",
                    read_only=False
                ))
        
        # Add read-only paths
        for path in fs_config.read_only_paths:
            if os.path.exists(path):
                mounts.append(Mount(
                    target=path,
                    source=path,
                    type="bind",
                    read_only=True
                ))
        
        # Add temp directory
        mounts.append(Mount(
            target="/tmp/workspace",
            source=self.temp_dir,
            type="bind",
            read_only=False
        ))
        
        # Prepare resource limits
        limits = self.sandbox_config.resource_limits
        
        # Create container
        container = client.containers.create(
            image=self.sandbox_config.container_image,
            name=f"mcp_{self.server_id}_{int(asyncio.get_event_loop().time())}",
            detach=True,
            mounts=mounts,
            environment=self.sandbox_config.environment_vars,
            cpu_percent=limits.max_cpu_percent,
            mem_limit=f"{limits.max_memory_mb}m",
            network_mode="none" if self.sandbox_config.network_config.policy == NetworkPolicy.DENY_ALL else "bridge",
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            cap_add=self.sandbox_config.allowed_capabilities,
        )
        
        self.container_id = container.id
        logger.info(f"Created container {self.container_id} for server {self.server_id}")
    
    async def _cleanup_container(self) -> None:
        """Clean up Docker container."""
        try:
            import docker
            client = docker.from_env()
            
            container = client.containers.get(self.container_id)
            container.stop(timeout=10)
            container.remove()
            
            logger.info(f"Cleaned up container {self.container_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup container: {e}")
    
    async def _setup_process_isolation(self) -> None:
        """Set up process-level isolation (fallback when containers not available)."""
        # This is a simplified version - in production you'd want to use
        # OS-specific features like cgroups, namespaces, etc.
        logger.info(f"Using process isolation for server {self.server_id}")
        
        # Set up filesystem restrictions
        fs_config = self.sandbox_config.filesystem_config
        if fs_config.policy == FilesystemPolicy.RESTRICTED:
            # In a real implementation, you'd use OS features to restrict access
            # For now, we'll just log the configuration
            logger.info(f"Filesystem restrictions: allowed={fs_config.allowed_paths}, "
                       f"readonly={fs_config.read_only_paths}")
    
    def get_execution_command(self, original_command: str) -> str:
        """Get the command to execute in the sandboxed environment."""
        if not self.sandbox_config.enabled:
            return original_command
        
        if self.container_id:
            # Execute inside container
            return f"docker exec {self.container_id} {original_command}"
        else:
            # For process isolation, we could use tools like firejail, bubblewrap, etc.
            # For now, return the original command with environment restrictions
            return original_command
    
    def get_environment_vars(self) -> Dict[str, str]:
        """Get environment variables for the sandboxed process."""
        env = self.sandbox_config.environment_vars.copy()
        
        # Add sandbox-specific variables
        env["MCP_SANDBOX"] = "1"
        env["MCP_SERVER_ID"] = self.server_id
        
        if self.temp_dir:
            env["TMPDIR"] = self.temp_dir
            env["TEMP"] = self.temp_dir
            env["TMP"] = self.temp_dir
        
        return env


class MCPSandbox:
    """Main sandboxing manager for MCP servers."""
    
    def __init__(self):
        self.environments: Dict[str, IsolatedEnvironment] = {}
        self._lock = asyncio.Lock()
    
    async def create_environment(self, 
                                server_id: str, 
                                sandbox_config: SandboxConfig) -> IsolatedEnvironment:
        """Create a new isolated environment for an MCP server."""
        async with self._lock:
            if server_id in self.environments:
                raise ValueError(f"Environment for server {server_id} already exists")
            
            env = IsolatedEnvironment(server_id, sandbox_config)
            await env.setup()
            
            self.environments[server_id] = env
            return env
    
    async def destroy_environment(self, server_id: str) -> None:
        """Destroy an isolated environment."""
        async with self._lock:
            if server_id not in self.environments:
                return
            
            env = self.environments[server_id]
            await env.cleanup()
            
            del self.environments[server_id]
    
    def get_environment(self, server_id: str) -> Optional[IsolatedEnvironment]:
        """Get an existing isolated environment."""
        return self.environments.get(server_id)
    
    async def cleanup_all(self) -> None:
        """Clean up all environments."""
        async with self._lock:
            for server_id in list(self.environments.keys()):
                try:
                    env = self.environments[server_id]
                    await env.cleanup()
                except Exception as e:
                    logger.error(f"Failed to cleanup environment for {server_id}: {e}")
            
            self.environments.clear()


# Preset sandbox configurations
SANDBOX_PRESETS = {
    "strict": SandboxConfig(
        enabled=True,
        use_containers=True,
        network_config=NetworkConfig(policy=NetworkPolicy.DENY_ALL),
        filesystem_config=FilesystemConfig(
            policy=FilesystemPolicy.RESTRICTED,
            allowed_paths=["/tmp/mcp_workspace"],
            read_only_paths=[]
        ),
        resource_limits=ResourceLimits(
            max_cpu_percent=20,
            max_memory_mb=256,
            max_execution_time_seconds=60
        )
    ),
    "moderate": SandboxConfig(
        enabled=True,
        use_containers=True,
        network_config=NetworkConfig(
            policy=NetworkPolicy.RESTRICTED,
            allowed_domains=["api.github.com", "api.openai.com"]
        ),
        filesystem_config=FilesystemConfig(
            policy=FilesystemPolicy.RESTRICTED,
            allowed_paths=["/tmp/mcp_workspace", "/var/lightning/data"],
            read_only_paths=["/etc/lightning"]
        ),
        resource_limits=ResourceLimits(
            max_cpu_percent=50,
            max_memory_mb=512,
            max_execution_time_seconds=300
        )
    ),
    "relaxed": SandboxConfig(
        enabled=True,
        use_containers=False,
        network_config=NetworkConfig(policy=NetworkPolicy.ALLOW_ALL),
        filesystem_config=FilesystemConfig(
            policy=FilesystemPolicy.RESTRICTED,
            allowed_paths=["/tmp", "/var/lightning"],
            read_only_paths=["/etc"]
        ),
        resource_limits=ResourceLimits(
            max_cpu_percent=80,
            max_memory_mb=1024,
            max_execution_time_seconds=600
        )
    ),
    "disabled": SandboxConfig(enabled=False)
}