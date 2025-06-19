"""OpenRouter LLM provider implementation."""

import os
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional
import logging
import httpx
import json

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


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider implementation for accessing various LLM models."""
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    # Popular models available on OpenRouter (subset)
    SUPPORTED_MODELS = {
        # OpenAI models
        "openai/gpt-4o": {"multiplier": 1.0},
        "openai/gpt-4o-mini": {"multiplier": 1.0},
        "openai/gpt-4-turbo": {"multiplier": 1.0},
        "openai/gpt-4": {"multiplier": 1.0},
        "openai/gpt-3.5-turbo": {"multiplier": 1.0},
        "openai/o1-preview": {"multiplier": 1.0},
        "openai/o1-mini": {"multiplier": 1.0},
        
        # Anthropic models
        "anthropic/claude-3.5-sonnet": {"multiplier": 1.0},
        "anthropic/claude-3-opus": {"multiplier": 1.0},
        "anthropic/claude-3-sonnet": {"multiplier": 1.0},
        "anthropic/claude-3-haiku": {"multiplier": 1.0},
        
        # Google models
        "google/gemini-pro-1.5": {"multiplier": 1.0},
        "google/gemini-pro": {"multiplier": 1.0},
        "google/gemini-flash-1.5": {"multiplier": 1.0},
        
        # Meta models
        "meta-llama/llama-3.1-405b-instruct": {"multiplier": 1.0},
        "meta-llama/llama-3.1-70b-instruct": {"multiplier": 1.0},
        "meta-llama/llama-3.1-8b-instruct": {"multiplier": 1.0},
        
        # Mistral models
        "mistralai/mistral-large": {"multiplier": 1.0},
        "mistralai/mixtral-8x22b-instruct": {"multiplier": 1.0},
        "mistralai/mixtral-8x7b-instruct": {"multiplier": 1.0},
        
        # Others
        "cohere/command-r-plus": {"multiplier": 1.0},
        "perplexity/llama-3.1-sonar-large-128k-online": {"multiplier": 1.0},
    }
    
    def __init__(self, config: LLMProviderConfig):
        """Initialize OpenRouter provider."""
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENROUTER_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenRouter API key is required")
        
        self.base_url = config.base_url or self.BASE_URL
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        self.site_url = config.extra_config.get("site_url", "https://lightning.ai")
        self.site_name = config.extra_config.get("site_name", "Lightning AI")
    
    def _get_headers(self, user: Optional[str] = None) -> Dict[str, str]:
        """Get headers for OpenRouter API requests."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
        }
        if user:
            headers["X-User-Id"] = user
        return headers
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert our Message format to OpenRouter format."""
        openrouter_messages = []
        for msg in messages:
            openrouter_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.name:
                openrouter_msg["name"] = msg.name
            if msg.tool_calls:
                openrouter_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                openrouter_msg["tool_call_id"] = msg.tool_call_id
            openrouter_messages.append(openrouter_msg)
        return openrouter_messages
    
    def _parse_sse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a server-sent event line."""
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                return None
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse SSE data: {data}")
                return None
        return None
    
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion using OpenRouter."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Build OpenRouter request
                openrouter_request = {
                    "model": request.model,
                    "messages": self._convert_messages(request.messages),
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "frequency_penalty": request.frequency_penalty,
                    "presence_penalty": request.presence_penalty,
                    "stream": False,
                }
                
                if request.max_tokens:
                    openrouter_request["max_tokens"] = request.max_tokens
                if request.stop:
                    openrouter_request["stop"] = request.stop
                if request.tools:
                    openrouter_request["tools"] = request.tools
                if request.tool_choice:
                    openrouter_request["tool_choice"] = request.tool_choice
                if request.response_format:
                    openrouter_request["response_format"] = request.response_format
                if request.seed:
                    openrouter_request["seed"] = request.seed
                
                # Add any extra provider-specific params
                openrouter_request.update(request.metadata)
                
                # Make the API call
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(request.user),
                    json=openrouter_request,
                )
                response.raise_for_status()
                data = response.json()
                
                # Convert response
                choices = []
                for choice in data["choices"]:
                    msg = Message(
                        role=MessageRole(choice["message"]["role"]),
                        content=choice["message"].get("content", ""),
                        tool_calls=choice["message"].get("tool_calls"),
                    )
                    choices.append(CompletionChoice(
                        index=choice["index"],
                        message=msg,
                        finish_reason=choice.get("finish_reason"),
                    ))
                
                usage = None
                if "usage" in data:
                    # OpenRouter provides cost directly
                    cost = data["usage"].get("total_cost", 0.0)
                    usage = CompletionUsage(
                        prompt_tokens=data["usage"]["prompt_tokens"],
                        completion_tokens=data["usage"]["completion_tokens"],
                        total_tokens=data["usage"]["total_tokens"],
                        cost=cost,
                    )
                
                return CompletionResponse(
                    id=data["id"],
                    model=data["model"],
                    created=datetime.fromtimestamp(data["created"]),
                    choices=choices,
                    usage=usage,
                    system_fingerprint=data.get("system_fingerprint"),
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"OpenRouter completion error: {e}")
                raise
    
    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[StreamResponse]:
        """Generate a streaming completion using OpenRouter."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Build OpenRouter request
                openrouter_request = {
                    "model": request.model,
                    "messages": self._convert_messages(request.messages),
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "frequency_penalty": request.frequency_penalty,
                    "presence_penalty": request.presence_penalty,
                    "stream": True,
                }
                
                if request.max_tokens:
                    openrouter_request["max_tokens"] = request.max_tokens
                if request.stop:
                    openrouter_request["stop"] = request.stop
                if request.tools:
                    openrouter_request["tools"] = request.tools
                if request.tool_choice:
                    openrouter_request["tool_choice"] = request.tool_choice
                if request.response_format:
                    openrouter_request["response_format"] = request.response_format
                if request.seed:
                    openrouter_request["seed"] = request.seed
                
                # Add any extra provider-specific params
                openrouter_request.update(request.metadata)
                
                # Make the streaming API call
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(request.user),
                    json=openrouter_request,
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            data = self._parse_sse_line(line)
                            if data is None:
                                continue
                            
                            choices = []
                            for choice in data.get("choices", []):
                                delta_data = choice.get("delta", {})
                                delta = StreamDelta(
                                    content=delta_data.get("content"),
                                    role=MessageRole(delta_data["role"]) if "role" in delta_data else None,
                                    tool_calls=delta_data.get("tool_calls"),
                                )
                                choices.append(StreamChoice(
                                    index=choice["index"],
                                    delta=delta,
                                    finish_reason=choice.get("finish_reason"),
                                ))
                            
                            yield StreamResponse(
                                id=data["id"],
                                model=data["model"],
                                created=datetime.fromtimestamp(data["created"]),
                                choices=choices,
                            )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"OpenRouter streaming HTTP error: {e.response.status_code}")
                raise
            except Exception as e:
                logger.error(f"OpenRouter streaming error: {e}")
                raise
    
    async def list_models(self) -> List[str]:
        """List available models from OpenRouter."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract model IDs
                model_ids = [model["id"] for model in data.get("data", [])]
                return model_ids
                
            except Exception as e:
                logger.error(f"Error listing OpenRouter models: {e}")
                # Return known models as fallback
                return list(self.SUPPORTED_MODELS.keys())
    
    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports the given model."""
        # OpenRouter supports many models, so we'll be permissive
        # and assume any model with a provider prefix is supported
        return "/" in model_id or model_id in self.SUPPORTED_MODELS
    
    async def validate_api_key(self) -> bool:
        """Validate the API key by making a simple API call."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._get_headers(),
                )
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Error validating OpenRouter API key: {e}")
                return False