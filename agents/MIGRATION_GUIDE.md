# Agent Migration Guide: Using Lightning Core Model Registry

This guide helps agents migrate from direct OpenAI usage to the Lightning Core model registry and completions API.

## Overview

Lightning Core now provides a centralized model registry that:
- Supports multiple LLM providers (OpenAI, OpenRouter, Anthropic via OpenRouter, etc.)
- Tracks usage and costs per user/agent
- Provides a unified API for all models
- Enables easy model switching and A/B testing

## For Python Agents

### Before (Direct OpenAI)
```python
import openai

openai.api_key = "your-key"
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### After (Lightning Core)

#### Option 1: Using the Lightning Client
```python
from lightning_client import LightningClient, Message

client = LightningClient(agent_id="my_agent")

# Simple completion
response = await client.complete(
    messages=[Message(role="user", content="Hello")],
    model="gpt-4o-mini"
)

# Or use the sync wrapper
from lightning_client import complete_sync
result = complete_sync("Hello", model="gpt-4o-mini")
```

#### Option 2: Using the AgentDriver Base Class
```python
from lightning_core.vextir_os.drivers import AgentDriver

class MyAgent(AgentDriver):
    async def process_task(self, task: str):
        # Uses model registry automatically
        response = await self.complete(
            messages=[{"role": "user", "content": task}],
            temperature=0.7
        )
        return response
```

## For TypeScript/Node.js Agents

### Before (Direct OpenAI)
```typescript
import OpenAI from 'openai';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
const response = await openai.chat.completions.create({
    model: "gpt-4",
    messages: [{ role: "user", content: "Hello" }]
});
```

### After (Lightning Core)

#### Using HTTP API Directly
```typescript
const LIGHTNING_API_URL = process.env.LIGHTNING_API_URL || 'http://localhost:8000';

async function complete(messages: any[], model = 'gpt-4o-mini') {
    const response = await fetch(`${LIGHTNING_API_URL}/completions`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Agent-Id': 'my_agent'
        },
        body: JSON.stringify({
            model,
            messages,
            temperature: 0.7
        })
    });
    
    return response.json();
}

// Usage
const result = await complete([
    { role: 'user', content: 'Hello' }
]);
```

#### OpenAI-Compatible Endpoint
```typescript
// Lightning Core provides an OpenAI-compatible endpoint
// Just change the base URL:
const openai = new OpenAI({ 
    apiKey: 'your-lightning-key',
    baseURL: 'http://localhost:8000/v1'
});

// Rest of the code remains the same!
const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "Hello" }]
});
```

## Available Models

### Via OpenAI Provider
- `gpt-4o` - Latest GPT-4 Optimized
- `gpt-4o-mini` - Smaller, faster GPT-4 variant
- `gpt-4-turbo` - GPT-4 Turbo
- `o1-preview` - O1 reasoning model
- `o1-mini` - Smaller O1 model
- `o3-mini` - O3 mini model

### Via OpenRouter Provider
- `claude-sonnet-4` - Claude 3.5 Sonnet
- `claude-3-opus` - Claude 3 Opus
- `gemini-pro-1.5` - Google Gemini Pro 1.5
- `llama-3.1-405b` - Meta Llama 3.1 405B
- Many more available

## Configuration

### Environment Variables
```bash
# For Python agents
export LIGHTNING_API_URL=http://localhost:8000
export LIGHTNING_API_KEY=your-key-if-required

# The API will use these if available:
export OPENAI_API_KEY=your-openai-key
export OPENROUTER_API_KEY=your-openrouter-key
```

### Agent Registration
```python
# Register your agent for better tracking
client = LightningClient()
await client.register_agent(
    agent_id="conseil_assistant",
    agent_name="Conseil Coding Assistant",
    default_model="gpt-4o-mini",
    capabilities=["coding", "debugging", "documentation"]
)
```

## Benefits of Migration

1. **Multi-Provider Support**: Access models from OpenAI, Anthropic, Google, Meta, etc.
2. **Cost Tracking**: Automatic usage and cost tracking per agent/user
3. **Model Flexibility**: Easy to switch models or A/B test
4. **Centralized Configuration**: Manage API keys and models in one place
5. **Built-in Retries**: Automatic retry logic and error handling
6. **Usage Analytics**: Track which models perform best for different tasks

## API Endpoints

- `GET /models` - List available models
- `GET /models/{model_id}` - Get model information
- `POST /completions` - Create completion
- `GET /usage/stats` - Get usage statistics
- `POST /agents/register` - Register agent
- `POST /v1/chat/completions` - OpenAI-compatible endpoint

## Streaming Support

```python
# Python streaming
async for chunk in client.complete(messages, stream=True):
    print(chunk['choices'][0]['delta']['content'], end='')
```

```typescript
// TypeScript streaming
const response = await fetch(`${LIGHTNING_API_URL}/completions`, {
    method: 'POST',
    headers: { 
        'Content-Type': 'application/json',
        'X-Agent-Id': 'my_agent'
    },
    body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages,
        stream: true
    })
});

const reader = response.body.getReader();
// Process SSE stream...
```

## Migration Checklist

- [ ] Remove direct OpenAI/Anthropic client initialization
- [ ] Replace API calls with Lightning Core client
- [ ] Update environment variables
- [ ] Register agent with Lightning Core
- [ ] Test with different models
- [ ] Monitor usage statistics

## Support

For questions or issues:
- Check the API health: `GET /health`
- View API docs: Visit `http://localhost:8000/docs`
- Check model availability: `GET /models`