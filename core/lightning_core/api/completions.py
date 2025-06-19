"""HTTP API endpoints for the completions service."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
import asyncio

from ..llm import get_completions_api, Message, MessageRole
from ..vextir_os.registries import get_model_registry

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Lightning Completions API", version="1.0.0")


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role (system, user, assistant, tool)")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Optional name for the message")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID")


class CompletionRequest(BaseModel):
    """Completion request model."""
    model: str = Field(..., description="Model ID to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: float = Field(0.7, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    top_p: float = Field(1.0, description="Top-p sampling")
    frequency_penalty: float = Field(0.0, description="Frequency penalty")
    presence_penalty: float = Field(0.0, description="Presence penalty")
    stream: bool = Field(False, description="Whether to stream the response")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Available tools")
    tool_choice: Optional[Any] = Field(None, description="Tool choice preference")
    user: Optional[str] = Field(None, description="User ID for tracking")


class CompletionResponse(BaseModel):
    """Completion response model."""
    id: str
    model: str
    created: int
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    name: str
    provider: str
    capabilities: List[str]
    context_window: int
    max_output_tokens: int
    cost_per_1k_tokens: Dict[str, float]
    supports_streaming: bool


class UsageStats(BaseModel):
    """Usage statistics."""
    total_requests: int
    total_tokens: int
    total_cost: float
    requests_by_model: Dict[str, int]
    tokens_by_model: Dict[str, int]
    cost_by_model: Dict[str, float]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "completions"}


@app.get("/models", response_model=List[str])
async def list_models(
    provider: Optional[str] = None,
    capability: Optional[str] = None,
):
    """List available models."""
    api = get_completions_api()
    return api.list_models(provider=provider, capability=capability)


@app.get("/models/{model_id}", response_model=Optional[ModelInfo])
async def get_model_info(model_id: str):
    """Get information about a specific model."""
    api = get_completions_api()
    info = api.get_model_info(model_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return info


@app.post("/completions", response_model=CompletionResponse)
async def create_completion(
    request: CompletionRequest,
    x_user_id: Optional[str] = Header(None, description="User ID for tracking"),
    x_agent_id: Optional[str] = Header(None, description="Agent ID for tracking"),
):
    """Create a completion."""
    api = get_completions_api()
    
    # Convert messages to Message objects
    messages = []
    for msg in request.messages:
        messages.append(Message(
            role=MessageRole(msg.role),
            content=msg.content,
            name=msg.name,
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
        ))
    
    # Determine user ID for tracking
    user_id = request.user or x_user_id or x_agent_id or "anonymous"
    
    try:
        if request.stream:
            # Return streaming response
            return StreamingResponse(
                _stream_completion(api, request, messages, user_id),
                media_type="text/event-stream",
            )
        else:
            # Regular completion
            response = await api.create(
                model=request.model,
                messages=messages,
                user_id=user_id,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                frequency_penalty=request.frequency_penalty,
                presence_penalty=request.presence_penalty,
                tools=request.tools,
                tool_choice=request.tool_choice,
            )
            
            # Convert response to dict format
            return CompletionResponse(
                id=response.id,
                model=response.model,
                created=int(response.created.timestamp()),
                choices=[{
                    "index": choice.index,
                    "message": {
                        "role": choice.message.role.value,
                        "content": choice.message.content,
                        "tool_calls": choice.message.tool_calls,
                    },
                    "finish_reason": choice.finish_reason,
                } for choice in response.choices],
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                } if response.usage else None,
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating completion: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _stream_completion(api, request, messages, user_id):
    """Stream completion responses."""
    try:
        stream = await api.create(
            model=request.model,
            messages=messages,
            user_id=user_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            frequency_penalty=request.frequency_penalty,
            presence_penalty=request.presence_penalty,
            tools=request.tools,
            tool_choice=request.tool_choice,
            stream=True,
        )
        
        async for chunk in stream:
            # Convert to SSE format
            data = {
                "id": chunk.id,
                "model": chunk.model,
                "created": int(chunk.created.timestamp()),
                "choices": [{
                    "index": choice.index,
                    "delta": {
                        "role": choice.delta.role.value if choice.delta.role else None,
                        "content": choice.delta.content,
                        "tool_calls": choice.delta.tool_calls,
                    },
                    "finish_reason": choice.finish_reason,
                } for choice in chunk.choices],
            }
            
            yield f"data: {json.dumps(data)}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Error streaming completion: {e}")
        error_data = {"error": {"message": str(e), "type": "streaming_error"}}
        yield f"data: {json.dumps(error_data)}\n\n"


@app.get("/usage/stats", response_model=UsageStats)
async def get_usage_stats(
    x_user_id: Optional[str] = Header(None, description="User ID for filtering"),
):
    """Get usage statistics."""
    api = get_completions_api()
    stats = api.get_usage_stats(user_id=x_user_id)
    return UsageStats(**stats)


@app.post("/agents/register")
async def register_agent(
    agent_id: str,
    agent_name: str,
    default_model: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
):
    """Register an agent with the system."""
    # TODO: Implement agent registration
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "registered": True,
        "default_model": default_model or "gpt-4o-mini",
    }


# OpenAI-compatible endpoints for drop-in replacement
@app.post("/v1/chat/completions", response_model=CompletionResponse)
async def openai_compatible_completion(
    request: CompletionRequest,
    authorization: Optional[str] = Header(None),
):
    """OpenAI-compatible chat completions endpoint."""
    # Extract user ID from authorization header if present
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        # Could parse JWT or API key to get user ID
        user_id = "openai-compat"
    
    return await create_completion(request, x_user_id=user_id, x_agent_id=None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)