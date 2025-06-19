"""Abstract LLM provider interface following Lightning's provider pattern."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from enum import Enum


class MessageRole(str, Enum):
    """Role of a message in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Represents a message in a conversation."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class CompletionChoice:
    """Represents a single completion choice."""
    index: int
    message: Message
    finish_reason: Optional[str] = None


@dataclass
class CompletionUsage:
    """Token usage information for a completion."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: Optional[float] = None  # Cost in USD


@dataclass
class CompletionResponse:
    """Response from a completion request."""
    id: str
    model: str
    created: datetime
    choices: List[CompletionChoice]
    usage: Optional[CompletionUsage] = None
    system_fingerprint: Optional[str] = None


@dataclass
class StreamDelta:
    """Delta content for streaming responses."""
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    role: Optional[MessageRole] = None


@dataclass
class StreamChoice:
    """Represents a choice in a streaming response."""
    index: int
    delta: StreamDelta
    finish_reason: Optional[str] = None


@dataclass
class StreamResponse:
    """Response chunk from a streaming completion."""
    id: str
    model: str
    created: datetime
    choices: List[StreamChoice]


@dataclass
class CompletionRequest:
    """Request for a completion."""
    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = None  # For tracking usage per user
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional provider-specific params


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion for the given request."""
        pass
    
    @abstractmethod
    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[StreamResponse]:
        """Generate a streaming completion for the given request."""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[str]:
        """List available models from this provider."""
        pass
    
    @abstractmethod
    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports the given model."""
        pass
    
    @abstractmethod
    async def validate_api_key(self) -> bool:
        """Validate that the API key/credentials are valid."""
        pass


@dataclass
class LLMProviderConfig:
    """Configuration for an LLM provider."""
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    timeout: int = 60
    max_retries: int = 3
    extra_config: Dict[str, Any] = field(default_factory=dict)