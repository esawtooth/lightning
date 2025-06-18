"""
Serverless runtime abstraction layer for Lightning Core.

Provides abstract base classes for serverless function execution,
supporting both cloud (e.g., Azure Functions) and local implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
import json


class TriggerType(Enum):
    """Function trigger types."""
    HTTP = "http"
    EVENT = "event"
    TIMER = "timer"
    QUEUE = "queue"
    BLOB = "blob"
    MANUAL = "manual"


class RuntimeType(Enum):
    """Function runtime types."""
    PYTHON = "python"
    NODE = "node"
    DOTNET = "dotnet"
    JAVA = "java"
    CUSTOM = "custom"


@dataclass
class FunctionConfig:
    """Serverless function configuration."""
    name: str
    handler: str  # e.g., "main.handler" or "index.handler"
    runtime: RuntimeType = RuntimeType.PYTHON
    memory_mb: int = 256
    timeout_seconds: int = 300
    environment_variables: Dict[str, str] = field(default_factory=dict)
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    code_path: Optional[str] = None
    entry_point: Optional[str] = None
    
    def add_http_trigger(
        self,
        methods: List[str] = None,
        route: str = "/{*path}",
        auth_level: str = "anonymous"
    ) -> None:
        """Add an HTTP trigger to the function."""
        self.triggers.append({
            "type": TriggerType.HTTP.value,
            "methods": methods or ["GET", "POST"],
            "route": route,
            "auth_level": auth_level
        })
    
    def add_event_trigger(
        self,
        event_types: List[str],
        topic: Optional[str] = None
    ) -> None:
        """Add an event trigger to the function."""
        self.triggers.append({
            "type": TriggerType.EVENT.value,
            "event_types": event_types,
            "topic": topic
        })
    
    def add_timer_trigger(self, cron_expression: str) -> None:
        """Add a timer trigger to the function."""
        self.triggers.append({
            "type": TriggerType.TIMER.value,
            "schedule": cron_expression
        })


@dataclass
class FunctionContext:
    """Context provided to serverless functions."""
    function_name: str
    invocation_id: str
    trigger_type: TriggerType
    trigger_data: Dict[str, Any]
    environment: Dict[str, str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionResponse:
    """Response from serverless function execution."""
    status_code: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    is_error: bool = False
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            "status_code": self.status_code,
            "body": self.body,
            "headers": self.headers,
            "is_error": self.is_error,
            "error_message": self.error_message,
            "logs": self.logs
        }


FunctionHandler = Callable[[FunctionContext], Awaitable[FunctionResponse]]


class ServerlessRuntime(ABC):
    """Abstract base class for serverless runtime implementations."""
    
    @abstractmethod
    async def deploy_function(
        self,
        config: FunctionConfig,
        handler: FunctionHandler
    ) -> str:
        """
        Deploy a serverless function.
        Returns the function ID/ARN.
        """
        pass
    
    @abstractmethod
    async def invoke_function(
        self,
        function_id: str,
        payload: Dict[str, Any],
        async_invoke: bool = False
    ) -> FunctionResponse:
        """Invoke a serverless function."""
        pass
    
    @abstractmethod
    async def update_function(
        self,
        function_id: str,
        config: Optional[FunctionConfig] = None,
        handler: Optional[FunctionHandler] = None
    ) -> None:
        """Update function configuration or code."""
        pass
    
    @abstractmethod
    async def delete_function(self, function_id: str) -> None:
        """Delete a serverless function."""
        pass
    
    @abstractmethod
    async def list_functions(
        self,
        name_prefix: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """List deployed functions."""
        pass
    
    @abstractmethod
    async def get_function(self, function_id: str) -> Optional[Dict[str, Any]]:
        """Get function information."""
        pass
    
    @abstractmethod
    async def get_function_logs(
        self,
        function_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get function execution logs."""
        pass
    
    @abstractmethod
    async def set_function_concurrency(
        self,
        function_id: str,
        reserved_concurrency: Optional[int] = None
    ) -> None:
        """Set function concurrency limits."""
        pass
    
    @abstractmethod
    async def create_function_url(
        self,
        function_id: str,
        cors_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a public URL for the function.
        Returns the function URL.
        """
        pass
    
    @abstractmethod
    async def register_event_source(
        self,
        function_id: str,
        event_source_config: Dict[str, Any]
    ) -> str:
        """
        Register an event source for the function.
        Returns the event source mapping ID.
        """
        pass
    
    @abstractmethod
    async def unregister_event_source(
        self,
        event_source_id: str
    ) -> None:
        """Unregister an event source."""
        pass