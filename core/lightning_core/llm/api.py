"""Internal completions API for agents to use."""

import logging
from typing import AsyncIterator, Dict, List, Optional, Union

from ..abstractions.llm import (
    Message, MessageRole, CompletionResponse, StreamResponse
)
from ..vextir_os.registries import get_model_registry, ModelRegistry

logger = logging.getLogger(__name__)


class CompletionsAPI:
    """
    Unified completions API for agents to interact with LLM models.
    
    This API provides a consistent interface for agents to make completion
    requests regardless of the underlying provider (OpenAI, OpenRouter, etc).
    """
    
    def __init__(self, model_registry: Optional[ModelRegistry] = None):
        """Initialize the completions API."""
        self.model_registry = model_registry or get_model_registry()
    
    async def create(
        self,
        model: str,
        messages: List[Union[Message, Dict[str, str]]],
        user_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[CompletionResponse, AsyncIterator[StreamResponse]]:
        """
        Create a completion request.
        
        Args:
            model: Model ID to use (e.g., "gpt-4o", "claude-sonnet-4")
            messages: List of messages (Message objects or dicts)
            user_id: User ID for tracking usage
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional model-specific parameters
            
        Returns:
            CompletionResponse if stream=False, AsyncIterator[StreamResponse] if stream=True
        """
        # Convert dict messages to Message objects
        message_objects = []
        for msg in messages:
            if isinstance(msg, dict):
                message_objects.append(Message(
                    role=MessageRole(msg["role"]),
                    content=msg["content"],
                    name=msg.get("name"),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                ))
            else:
                message_objects.append(msg)
        
        # Delegate to model registry
        if stream:
            return self.model_registry.stream_complete(
                model_id=model,
                messages=message_objects,
                user_id=user_id,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        else:
            return await self.model_registry.complete(
                model_id=model,
                messages=message_objects,
                user_id=user_id,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
    
    def list_models(self, provider: Optional[str] = None, capability: Optional[str] = None) -> List[str]:
        """
        List available models.
        
        Args:
            provider: Filter by provider (e.g., "openai", "openrouter")
            capability: Filter by capability (e.g., "chat", "vision", "function_calling")
            
        Returns:
            List of model IDs
        """
        models = self.model_registry.list_models(provider=provider, capability=capability)
        return [model.id for model in models]
    
    def get_model_info(self, model_id: str) -> Optional[Dict[str, any]]:
        """
        Get detailed information about a model.
        
        Args:
            model_id: Model ID to query
            
        Returns:
            Dictionary with model information or None if not found
        """
        model = self.model_registry.get_model(model_id)
        if not model:
            return None
            
        return {
            "id": model.id,
            "name": model.name,
            "provider": model.provider,
            "capabilities": model.capabilities,
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "cost_per_1k_tokens": model.cost_per_1k_tokens,
            "supports_streaming": model.supports_streaming,
        }
    
    def get_usage_stats(self, user_id: Optional[str] = None) -> Dict[str, any]:
        """
        Get usage statistics.
        
        Args:
            user_id: User ID to get stats for (None for all users)
            
        Returns:
            Dictionary with usage statistics
        """
        stats = self.model_registry.get_usage_stats(user_id)
        return {
            "total_requests": stats.total_requests,
            "total_tokens": stats.total_tokens,
            "total_cost": stats.total_cost,
            "requests_by_model": dict(stats.requests_by_model),
            "tokens_by_model": dict(stats.tokens_by_model),
            "cost_by_model": dict(stats.cost_by_model),
        }


# Global API instance
_global_completions_api: Optional[CompletionsAPI] = None


def get_completions_api() -> CompletionsAPI:
    """Get the global completions API instance."""
    global _global_completions_api
    if _global_completions_api is None:
        _global_completions_api = CompletionsAPI()
    return _global_completions_api