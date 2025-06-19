"""
Lightning Core Client for External Agents

This client provides a simple interface for external agents (TypeScript, Python, etc.)
to communicate with the Lightning Core completions API.
"""

import os
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, AsyncIterator
import httpx
from dataclasses import dataclass, asdict


@dataclass
class Message:
    """Chat message."""
    role: str  # system, user, assistant, tool
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class CompletionRequest:
    """Completion request."""
    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    user: Optional[str] = None


class LightningClient:
    """Client for Lightning Core completions API."""

    def __init__(
        self,
        base_url: str = None,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: int = 60,
    ):
        """
        Initialize Lightning client.

        Args:
            base_url: Base URL for Lightning Core API (defaults to env var or localhost)
            api_key: API key for authentication (optional)
            agent_id: Agent identifier for tracking
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("LIGHTNING_API_URL", "http://localhost:8000")
        self.api_key = api_key or os.getenv("LIGHTNING_API_KEY")
        self.agent_id = agent_id
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.agent_id:
            headers["X-Agent-Id"] = self.agent_id

        return headers

    async def complete(
        self,
        messages: List[Message],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        user: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a completion.

        Args:
            messages: List of messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Available tools for function calling
            tool_choice: Tool choice preference
            user: User ID for tracking
            stream: Whether to stream the response

        Returns:
            Completion response dict
        """
        request = CompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
            user=user,
        )

        # Convert dataclasses to dicts
        request_dict = asdict(request)
        request_dict["messages"] = [asdict(m) for m in messages]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if stream:
                return await self._stream_complete(client, request_dict)
            else:
                response = await client.post(
                    f"{self.base_url}/completions",
                    headers=self._get_headers(),
                    json=request_dict,
                )
                response.raise_for_status()
                return response.json()

    async def _stream_complete(
        self,
        client: httpx.AsyncClient,
        request_dict: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream completion responses."""
        async with client.stream(
            "POST",
            f"{self.base_url}/completions",
            headers=self._get_headers(),
            json=request_dict,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        self.logger.error(f"Failed to parse SSE data: {data}")

    async def list_models(
        self,
        provider: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> List[str]:
        """List available models."""
        params = {}
        if provider:
            params["provider"] = provider
        if capability:
            params["capability"] = capability

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/models",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a model."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/models/{model_id}",
                headers=self._get_headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def get_usage_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get usage statistics."""
        headers = self._get_headers()
        if user_id:
            headers["X-User-Id"] = user_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/usage/stats",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        default_model: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register an agent with Lightning Core."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/agents/register",
                headers=self._get_headers(),
                json={
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "default_model": default_model,
                    "capabilities": capabilities,
                },
            )
            response.raise_for_status()
            return response.json()


# Convenience functions for simple use cases

async def quick_complete(
    prompt: str,
    model: str = "gpt-4o-mini",
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """
    Quick completion for simple use cases.

    Args:
        prompt: User prompt
        model: Model to use
        system_prompt: Optional system prompt
        **kwargs: Additional arguments for complete()

    Returns:
        Assistant's response text
    """
    client = LightningClient()

    messages = []
    if system_prompt:
        messages.append(Message(role="system", content=system_prompt))
    messages.append(Message(role="user", content=prompt))

    response = await client.complete(messages=messages, model=model, **kwargs)
    return response["choices"][0]["message"]["content"]


def complete_sync(
    prompt: str,
    model: str = "gpt-4o-mini",
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """Synchronous wrapper for quick_complete."""
    return asyncio.run(quick_complete(prompt, model, system_prompt, **kwargs))


# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize client
        client = LightningClient(agent_id="example_agent")

        # List available models
        models = await client.list_models()
        print(f"Available models: {models}")

        # Get model info
        model_info = await client.get_model_info("gpt-4o-mini")
        print(f"Model info: {model_info}")

        # Create a completion
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="What is the capital of France?"),
        ]

        response = await client.complete(messages=messages, model="gpt-4o-mini")
        print(f"Response: {response['choices'][0]['message']['content']}")

        # Quick completion
        result = await quick_complete("Tell me a joke about programming")
        print(f"Joke: {result}")

    asyncio.run(main())
