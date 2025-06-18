"""
Docker-based container runtime implementation.

Uses Docker SDK for Python to manage containers locally.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import docker
from docker.models.containers import Container as DockerContainer
from docker.errors import DockerException, NotFound, APIError
import aiofiles
import tempfile
import os

from lightning_core.abstractions.container_runtime import (
    ContainerRuntime, Container, ContainerConfig, ContainerState, Port
)


logger = logging.getLogger(__name__)


class DockerContainerRuntime(ContainerRuntime):
    """Docker-based container runtime implementation."""
    
    def __init__(self, **kwargs: Any):
        self._client = docker.from_env()
        self._registry = kwargs.get("registry")
        self._registry_username = kwargs.get("registry_username")
        self._registry_password = kwargs.get("registry_password")
        self._network_name = kwargs.get("network_name", "lightning-network")
        
        # Create network if it doesn't exist
        self._ensure_network()
    
    def _ensure_network(self) -> None:
        """Ensure the Docker network exists."""
        try:
            self._client.networks.get(self._network_name)
        except NotFound:
            self._client.networks.create(self._network_name, driver="bridge")
            logger.info(f"Created Docker network: {self._network_name}")
    
    def _docker_to_container_state(self, status: str) -> ContainerState:
        """Convert Docker status to ContainerState."""
        status_map = {
            "created": ContainerState.PENDING,
            "restarting": ContainerState.PENDING,
            "running": ContainerState.RUNNING,
            "removing": ContainerState.TERMINATED,
            "paused": ContainerState.UNKNOWN,
            "exited": ContainerState.SUCCEEDED,
            "dead": ContainerState.FAILED,
        }
        return status_map.get(status.lower(), ContainerState.UNKNOWN)
    
    def _config_to_docker_params(self, config: ContainerConfig) -> Dict[str, Any]:
        """Convert ContainerConfig to Docker run parameters."""
        params = {
            "image": config.image,
            "name": config.name,
            "environment": config.environment_variables,
            "labels": config.labels,
            "working_dir": config.working_dir,
            "network": config.network_mode or self._network_name,
            "detach": True,
            "auto_remove": False,
        }
        
        # Command and args
        if config.command:
            params["command"] = config.command
        if config.args:
            if "command" in params:
                params["command"].extend(config.args)
            else:
                params["command"] = config.args
        
        # Ports
        if config.ports:
            params["ports"] = {}
            for port in config.ports:
                container_port = f"{port.port}/{port.protocol.lower()}"
                params["ports"][container_port] = port.port
        
        # Volumes
        if config.volumes:
            params["volumes"] = config.volumes
        
        # Resources
        if config.resources:
            params["mem_limit"] = f"{int(config.resources.memory_gb * 1024)}m"
            params["cpu_quota"] = int(config.resources.cpu * 100000)
            params["cpu_period"] = 100000
            
            if config.resources.gpu_count > 0:
                params["device_requests"] = [
                    docker.types.DeviceRequest(
                        count=config.resources.gpu_count,
                        capabilities=[["gpu"]]
                    )
                ]
        
        # Restart policy
        restart_policies = {
            "Always": {"Name": "always"},
            "OnFailure": {"Name": "on-failure", "MaximumRetryCount": 3},
            "Never": {"Name": "no"},
        }
        params["restart_policy"] = restart_policies.get(
            config.restart_policy,
            {"Name": "on-failure", "MaximumRetryCount": 3}
        )
        
        # DNS
        if config.dns_servers:
            params["dns"] = config.dns_servers
        
        return params
    
    def _docker_to_container(
        self,
        docker_container: DockerContainer,
        config: Optional[ContainerConfig] = None
    ) -> Container:
        """Convert Docker container to Container object."""
        attrs = docker_container.attrs
        
        # Extract state information
        state = self._docker_to_container_state(docker_container.status)
        
        # Get IP address
        ip_address = None
        if docker_container.attrs.get("NetworkSettings", {}).get("Networks"):
            for network in docker_container.attrs["NetworkSettings"]["Networks"].values():
                if network.get("IPAddress"):
                    ip_address = network["IPAddress"]
                    break
        
        # Get exit code
        exit_code = attrs.get("State", {}).get("ExitCode")
        
        # Get timestamps
        started_at = attrs.get("State", {}).get("StartedAt")
        finished_at = attrs.get("State", {}).get("FinishedAt")
        
        # Create container object
        container = Container(
            id=docker_container.id,
            name=docker_container.name,
            state=state,
            config=config or self._extract_config_from_docker(docker_container),
            ip_address=ip_address,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            metadata={
                "docker_status": docker_container.status,
                "docker_attrs": attrs
            }
        )
        
        return container
    
    def _extract_config_from_docker(self, docker_container: DockerContainer) -> ContainerConfig:
        """Extract ContainerConfig from Docker container."""
        attrs = docker_container.attrs
        config_data = attrs.get("Config", {})
        
        config = ContainerConfig(
            name=docker_container.name,
            image=config_data.get("Image", ""),
            command=config_data.get("Cmd"),
            environment_variables=dict(
                env.split("=", 1) for env in config_data.get("Env", [])
                if "=" in env
            ),
            working_dir=config_data.get("WorkingDir"),
            labels=config_data.get("Labels", {})
        )
        
        return config
    
    async def create_container(
        self,
        config: ContainerConfig,
        wait_for_ready: bool = True
    ) -> Container:
        """Create and start a new container."""
        # Run Docker operations in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        try:
            # Pull image if needed
            await self.pull_image(config.image)
            
            # Create container
            params = self._config_to_docker_params(config)
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.run(**params)
            )
            
            logger.info(f"Created container {config.name} with ID {docker_container.id}")
            
            # Wait for container to be ready if requested
            if wait_for_ready:
                await self._wait_for_ready(docker_container.id)
            
            # Refresh container info
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(docker_container.id)
            )
            
            return self._docker_to_container(docker_container, config)
            
        except DockerException as e:
            logger.error(f"Failed to create container {config.name}: {e}")
            raise
    
    async def _wait_for_ready(
        self,
        container_id: str,
        timeout: int = 30
    ) -> None:
        """Wait for container to be ready."""
        loop = asyncio.get_event_loop()
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                container = await loop.run_in_executor(
                    None,
                    lambda: self._client.containers.get(container_id)
                )
                
                if container.status == "running":
                    return
                elif container.status in ["exited", "dead"]:
                    raise RuntimeError(f"Container failed to start: {container.status}")
                
            except NotFound:
                raise RuntimeError(f"Container {container_id} not found")
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"Container {container_id} failed to become ready within {timeout} seconds")
    
    async def get_container(self, container_id: str) -> Optional[Container]:
        """Get container information by ID."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            return self._docker_to_container(docker_container)
        except NotFound:
            return None
    
    async def list_containers(
        self,
        labels: Optional[Dict[str, str]] = None,
        state: Optional[ContainerState] = None
    ) -> List[Container]:
        """List containers with optional filtering."""
        loop = asyncio.get_event_loop()
        
        filters = {}
        if labels:
            filters["label"] = [f"{k}={v}" for k, v in labels.items()]
        
        docker_containers = await loop.run_in_executor(
            None,
            lambda: self._client.containers.list(all=True, filters=filters)
        )
        
        containers = []
        for docker_container in docker_containers:
            container = self._docker_to_container(docker_container)
            if state is None or container.state == state:
                containers.append(container)
        
        return containers
    
    async def stop_container(
        self,
        container_id: str,
        timeout_seconds: int = 30
    ) -> None:
        """Stop a running container."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            await loop.run_in_executor(
                None,
                lambda: docker_container.stop(timeout=timeout_seconds)
            )
            
            logger.info(f"Stopped container {container_id}")
            
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            raise
    
    async def remove_container(
        self,
        container_id: str,
        force: bool = False
    ) -> None:
        """Remove a container."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            await loop.run_in_executor(
                None,
                lambda: docker_container.remove(force=force)
            )
            
            logger.info(f"Removed container {container_id}")
            
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to remove container {container_id}: {e}")
            raise
    
    async def get_container_logs(
        self,
        container_id: str,
        tail: Optional[int] = None,
        since: Optional[str] = None,
        follow: bool = False
    ) -> str:
        """Get container logs."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            kwargs = {
                "stdout": True,
                "stderr": True,
                "stream": False,
                "timestamps": True,
            }
            
            if tail:
                kwargs["tail"] = tail
            if since:
                kwargs["since"] = since
            
            logs = await loop.run_in_executor(
                None,
                lambda: docker_container.logs(**kwargs)
            )
            
            return logs.decode("utf-8") if isinstance(logs, bytes) else str(logs)
            
        except NotFound:
            return ""
        except DockerException as e:
            logger.error(f"Failed to get logs for container {container_id}: {e}")
            raise
    
    async def exec_command(
        self,
        container_id: str,
        command: List[str],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None
    ) -> tuple[int, str, str]:
        """Execute a command inside a running container."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            exec_kwargs = {
                "cmd": command,
                "stdout": True,
                "stderr": True,
                "stdin": False,
                "tty": False,
                "demux": True,
            }
            
            if working_dir:
                exec_kwargs["workdir"] = working_dir
            if environment:
                exec_kwargs["environment"] = environment
            
            result = await loop.run_in_executor(
                None,
                lambda: docker_container.exec_run(**exec_kwargs)
            )
            
            exit_code = result.exit_code
            stdout = result.output[0].decode("utf-8") if result.output[0] else ""
            stderr = result.output[1].decode("utf-8") if result.output[1] else ""
            
            return exit_code, stdout, stderr
            
        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to execute command in container {container_id}: {e}")
            raise
    
    async def pull_image(
        self,
        image: str,
        auth_config: Optional[Dict[str, str]] = None
    ) -> None:
        """Pull a container image."""
        loop = asyncio.get_event_loop()
        
        # Use provided auth or registry credentials
        if not auth_config and self._registry_username:
            auth_config = {
                "username": self._registry_username,
                "password": self._registry_password,
            }
        
        try:
            await loop.run_in_executor(
                None,
                lambda: self._client.images.pull(image, auth_config=auth_config)
            )
            logger.info(f"Pulled image: {image}")
        except APIError as e:
            if "not found" not in str(e).lower():
                logger.error(f"Failed to pull image {image}: {e}")
                raise
    
    async def push_image(
        self,
        image: str,
        auth_config: Optional[Dict[str, str]] = None
    ) -> None:
        """Push a container image to registry."""
        loop = asyncio.get_event_loop()
        
        # Use provided auth or registry credentials
        if not auth_config and self._registry_username:
            auth_config = {
                "username": self._registry_username,
                "password": self._registry_password,
            }
        
        try:
            await loop.run_in_executor(
                None,
                lambda: self._client.images.push(image, auth_config=auth_config)
            )
            logger.info(f"Pushed image: {image}")
        except DockerException as e:
            logger.error(f"Failed to push image {image}: {e}")
            raise
    
    async def build_image(
        self,
        context_path: str,
        dockerfile: str = "Dockerfile",
        tag: str = None,
        build_args: Optional[Dict[str, str]] = None
    ) -> str:
        """Build a container image."""
        loop = asyncio.get_event_loop()
        
        try:
            image, build_logs = await loop.run_in_executor(
                None,
                lambda: self._client.images.build(
                    path=context_path,
                    dockerfile=dockerfile,
                    tag=tag,
                    buildargs=build_args,
                    rm=True,
                )
            )
            
            # Log build output
            for log in build_logs:
                if "stream" in log:
                    logger.debug(log["stream"].strip())
            
            logger.info(f"Built image: {tag or image.id}")
            return image.id
            
        except DockerException as e:
            logger.error(f"Failed to build image: {e}")
            raise
    
    async def wait_for_container(
        self,
        container_id: str,
        timeout_seconds: Optional[int] = None
    ) -> int:
        """Wait for a container to finish."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            result = await loop.run_in_executor(
                None,
                lambda: docker_container.wait(timeout=timeout_seconds)
            )
            
            return result.get("StatusCode", -1)
            
        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to wait for container {container_id}: {e}")
            raise
    
    async def get_container_stats(
        self,
        container_id: str
    ) -> Dict[str, Any]:
        """Get container resource usage statistics."""
        loop = asyncio.get_event_loop()
        
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: self._client.containers.get(container_id)
            )
            
            stats = await loop.run_in_executor(
                None,
                lambda: docker_container.stats(stream=False)
            )
            
            # Extract relevant statistics
            cpu_stats = stats.get("cpu_stats", {})
            memory_stats = stats.get("memory_stats", {})
            
            return {
                "cpu_usage_percent": self._calculate_cpu_percent(cpu_stats, stats.get("precpu_stats", {})),
                "memory_usage_bytes": memory_stats.get("usage", 0),
                "memory_limit_bytes": memory_stats.get("limit", 0),
                "network_rx_bytes": sum(
                    net.get("rx_bytes", 0)
                    for net in stats.get("networks", {}).values()
                ),
                "network_tx_bytes": sum(
                    net.get("tx_bytes", 0)
                    for net in stats.get("networks", {}).values()
                ),
                "block_read_bytes": sum(
                    io.get("value", 0)
                    for io in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
                    if io.get("op") == "Read"
                ),
                "block_write_bytes": sum(
                    io.get("value", 0)
                    for io in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
                    if io.get("op") == "Write"
                ),
            }
            
        except NotFound:
            return {}
        except DockerException as e:
            logger.error(f"Failed to get stats for container {container_id}: {e}")
            return {}
    
    def _calculate_cpu_percent(
        self,
        cpu_stats: Dict[str, Any],
        precpu_stats: Dict[str, Any]
    ) -> float:
        """Calculate CPU usage percentage."""
        cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - \
                    precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - \
                       precpu_stats.get("system_cpu_usage", 0)
        
        if system_delta > 0 and cpu_delta > 0:
            cpu_count = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []))
            if cpu_count > 0:
                return (cpu_delta / system_delta) * cpu_count * 100.0
        
        return 0.0