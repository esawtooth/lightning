"""OpenAI LLM provider implementation."""

import os
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional
import logging

from openai import AsyncOpenAI
from openai.types import CompletionUsage as OpenAIUsage
from openai.types.chat import ChatCompletion, ChatCompletionChunk
import openai

from lightning_core.abstractions.llm import (
    LLMProvider,
    LLMProviderConfig,
    CompletionRequest,
    CompletionResponse,
    CompletionChoice,
    CompletionUsage,
    Message,
    MessageRole,
    StreamResponse,
    StreamChoice,
    StreamDelta,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""
    
    # Model pricing per 1k tokens (as of Dec 2024)
    PRICING = {
        # GPT-4o models
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-2024-08-06": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4o-mini-2024-07-18": {"input": 0.00015, "output": 0.0006},
        
        # GPT-4 models
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4-turbo-2024-04-09": {"input": 0.01, "output": 0.03},
        "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-32k": {"input": 0.06, "output": 0.12},
        
        # GPT-3.5 models
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
        
        # O1 models
        "o1-preview": {"input": 0.015, "output": 0.06},
        "o1-preview-2024-09-12": {"input": 0.015, "output": 0.06},
        "o1-mini": {"input": 0.003, "output": 0.012},
        "o1-mini-2024-09-12": {"input": 0.003, "output": 0.012},
        "o1": {"input": 0.015, "output": 0.06},
        "o3-mini": {"input": 0.0012, "output": 0.0048},  # Estimated
    }
    
    SUPPORTED_MODELS = set(PRICING.keys())
    
    def __init__(self, config: LLMProviderConfig):
        """Initialize OpenAI provider."""
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=config.base_url,
            organization=config.organization,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert our Message format to OpenAI format."""
        openai_messages = []
        for msg in messages:
            openai_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.name:
                openai_msg["name"] = msg.name
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
            openai_messages.append(openai_msg)
        return openai_messages
    
    def _calculate_cost(self, usage: OpenAIUsage, model: str) -> Optional[float]:
        """Calculate cost based on token usage."""
        if model not in self.PRICING:
            return None
        
        pricing = self.PRICING[model]
        input_cost = (usage.prompt_tokens / 1000) * pricing["input"]
        output_cost = (usage.completion_tokens / 1000) * pricing["output"]
        return input_cost + output_cost
    
    def _convert_response(self, response: ChatCompletion) -> CompletionResponse:
        """Convert OpenAI response to our format."""
        choices = []
        for choice in response.choices:
            msg = Message(
                role=MessageRole(choice.message.role),
                content=choice.message.content or "",
                tool_calls=choice.message.tool_calls if hasattr(choice.message, 'tool_calls') else None,
            )
            choices.append(CompletionChoice(
                index=choice.index,
                message=msg,
                finish_reason=choice.finish_reason,
            ))
        
        usage = None
        if response.usage:
            cost = self._calculate_cost(response.usage, response.model)
            usage = CompletionUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cost=cost,
            )
        
        return CompletionResponse(
            id=response.id,
            model=response.model,
            created=datetime.fromtimestamp(response.created),
            choices=choices,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )
    
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion using OpenAI."""
        try:
            # Build OpenAI request
            openai_request = {
                "model": request.model,
                "messages": self._convert_messages(request.messages),
                "temperature": request.temperature,
                "top_p": request.top_p,
                "frequency_penalty": request.frequency_penalty,
                "presence_penalty": request.presence_penalty,
                "stream": False,
            }
            
            if request.max_tokens:
                openai_request["max_tokens"] = request.max_tokens
            if request.stop:
                openai_request["stop"] = request.stop
            if request.tools:
                openai_request["tools"] = request.tools
            if request.tool_choice:
                openai_request["tool_choice"] = request.tool_choice
            if request.response_format:
                openai_request["response_format"] = request.response_format
            if request.seed:
                openai_request["seed"] = request.seed
            if request.user:
                openai_request["user"] = request.user
            
            # Add any extra provider-specific params
            openai_request.update(request.metadata)
            
            # Make the API call
            response = await self.client.chat.completions.create(**openai_request)
            
            # Convert and return response
            return self._convert_response(response)
            
        except Exception as e:
            logger.error(f"OpenAI completion error: {e}")
            raise
    
    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[StreamResponse]:
        """Generate a streaming completion using OpenAI."""
        try:
            # Build OpenAI request
            openai_request = {
                "model": request.model,
                "messages": self._convert_messages(request.messages),
                "temperature": request.temperature,
                "top_p": request.top_p,
                "frequency_penalty": request.frequency_penalty,
                "presence_penalty": request.presence_penalty,
                "stream": True,
            }
            
            if request.max_tokens:
                openai_request["max_tokens"] = request.max_tokens
            if request.stop:
                openai_request["stop"] = request.stop
            if request.tools:
                openai_request["tools"] = request.tools
            if request.tool_choice:
                openai_request["tool_choice"] = request.tool_choice
            if request.response_format:
                openai_request["response_format"] = request.response_format
            if request.seed:
                openai_request["seed"] = request.seed
            if request.user:
                openai_request["user"] = request.user
            
            # Add any extra provider-specific params
            openai_request.update(request.metadata)
            
            # Make the streaming API call
            stream = await self.client.chat.completions.create(**openai_request)
            
            async for chunk in stream:
                choices = []
                for choice in chunk.choices:
                    delta = StreamDelta(
                        content=choice.delta.content,
                        role=MessageRole(choice.delta.role) if choice.delta.role else None,
                        tool_calls=choice.delta.tool_calls if hasattr(choice.delta, 'tool_calls') else None,
                    )
                    choices.append(StreamChoice(
                        index=choice.index,
                        delta=delta,
                        finish_reason=choice.finish_reason,
                    ))
                
                yield StreamResponse(
                    id=chunk.id,
                    model=chunk.model,
                    created=datetime.fromtimestamp(chunk.created),
                    choices=choices,
                )
                
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise
    
    async def list_models(self) -> List[str]:
        """List available OpenAI models."""
        try:
            models = await self.client.models.list()
            model_ids = [model.id for model in models.data]
            # Filter to only chat models we support
            return [m for m in model_ids if m in self.SUPPORTED_MODELS]
        except Exception as e:
            logger.error(f"Error listing OpenAI models: {e}")
            # Return known models as fallback
            return list(self.SUPPORTED_MODELS)
    
    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports the given model."""
        return model_id in self.SUPPORTED_MODELS
    
    async def validate_api_key(self) -> bool:
        """Validate the API key by making a simple API call."""
        try:
            # Try to list models as a validation check
            await self.client.models.list()
            return True
        except openai.AuthenticationError:
            return False
        except Exception as e:
            logger.error(f"Error validating OpenAI API key: {e}")
            return False