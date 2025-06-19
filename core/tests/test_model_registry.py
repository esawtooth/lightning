"""Tests for the model registry and LLM providers."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from lightning_core.abstractions.llm import (
    LLMProviderConfig, Message, MessageRole, CompletionRequest,
    CompletionResponse, CompletionChoice, CompletionUsage
)
from lightning_core.providers.llm import OpenAIProvider, OpenRouterProvider
from lightning_core.vextir_os.registries import (
    ModelRegistry, ModelSpec, UsageRecord, UsageStats, get_model_registry
)
from lightning_core.llm import CompletionsAPI, get_completions_api


class TestModelRegistry:
    """Test the ModelRegistry class."""
    
    def test_registry_initialization(self):
        """Test that the registry initializes with default models."""
        registry = ModelRegistry()
        
        # Check that default models are loaded
        assert len(registry.models) > 0
        assert "gpt-4o" in registry.models
        assert "gpt-4o-mini" in registry.models
        assert "o1-mini" in registry.models
        assert "o3-mini" in registry.models
    
    def test_register_model(self):
        """Test registering a new model."""
        registry = ModelRegistry()
        
        model = ModelSpec(
            id="test-model",
            name="Test Model",
            provider="test",
            endpoint="https://test.com",
            capabilities=["chat"],
            cost_per_1k_tokens={"input": 0.01, "output": 0.02},
            context_window=4096,
            max_output_tokens=2048,
        )
        
        registry.register_model(model)
        assert "test-model" in registry.models
        assert registry.get_model("test-model") == model
    
    def test_list_models_with_filters(self):
        """Test listing models with filters."""
        registry = ModelRegistry()
        
        # Test provider filter
        openai_models = registry.list_models(provider="openai")
        assert all(m.provider == "openai" for m in openai_models)
        
        # Test capability filter
        chat_models = registry.list_models(capability="chat")
        assert all("chat" in m.capabilities for m in chat_models)
        
        # Test combined filters
        openai_chat_models = registry.list_models(provider="openai", capability="chat")
        assert all(m.provider == "openai" and "chat" in m.capabilities for m in openai_chat_models)
    
    def test_get_cheapest_model(self):
        """Test getting the cheapest model for a capability."""
        registry = ModelRegistry()
        
        # Get cheapest chat model
        cheapest = registry.get_cheapest_model("chat")
        assert cheapest is not None
        
        # Verify it's actually the cheapest
        all_chat_models = registry.get_models_by_capability("chat")
        total_costs = [
            m.cost_per_1k_tokens.get("input", 0) + m.cost_per_1k_tokens.get("output", 0)
            for m in all_chat_models
        ]
        min_cost = min(total_costs)
        cheapest_cost = (
            cheapest.cost_per_1k_tokens.get("input", 0) + 
            cheapest.cost_per_1k_tokens.get("output", 0)
        )
        assert cheapest_cost == min_cost
    
    def test_usage_tracking(self):
        """Test usage tracking functionality."""
        registry = ModelRegistry()
        
        # Create usage records
        record1 = UsageRecord(
            model_id="gpt-4o",
            user_id="user1",
            timestamp=datetime.now(),
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost=0.001,
            request_id="req1",
        )
        
        record2 = UsageRecord(
            model_id="gpt-4o-mini",
            user_id="user1",
            timestamp=datetime.now(),
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            cost=0.0005,
            request_id="req2",
        )
        
        # Track usage
        registry._track_usage(record1)
        registry._track_usage(record2)
        
        # Get user stats
        user_stats = registry.get_usage_stats("user1")
        assert user_stats.total_requests == 2
        assert user_stats.total_tokens == 450
        assert user_stats.total_cost == 0.0015
        assert user_stats.requests_by_model["gpt-4o"] == 1
        assert user_stats.requests_by_model["gpt-4o-mini"] == 1
        
        # Get overall stats
        overall_stats = registry.get_usage_stats()
        assert overall_stats.total_requests == 2
        assert overall_stats.total_tokens == 450


class TestOpenAIProvider:
    """Test the OpenAI provider."""
    
    @pytest.fixture
    def provider(self):
        """Create an OpenAI provider instance."""
        config = LLMProviderConfig(
            provider_type="openai",
            api_key="test-key",
        )
        return OpenAIProvider(config)
    
    def test_provider_initialization(self, provider):
        """Test provider initialization."""
        assert provider.config.provider_type == "openai"
        assert provider.api_key == "test-key"
        assert provider.client is not None
    
    def test_supports_model(self, provider):
        """Test model support checking."""
        assert provider.supports_model("gpt-4o")
        assert provider.supports_model("gpt-4o-mini")
        assert provider.supports_model("o1-preview")
        assert not provider.supports_model("unknown-model")
    
    def test_convert_messages(self, provider):
        """Test message conversion."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi there!"),
        ]
        
        converted = provider._convert_messages(messages)
        assert len(converted) == 3
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful"
        assert converted[1]["role"] == "user"
        assert converted[2]["role"] == "assistant"
    
    def test_calculate_cost(self, provider):
        """Test cost calculation."""
        usage = Mock(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        
        # Test known model
        cost = provider._calculate_cost(usage, "gpt-4o")
        expected_cost = (1000/1000) * 0.0025 + (500/1000) * 0.01  # Based on pricing
        assert cost == expected_cost
        
        # Test unknown model
        cost = provider._calculate_cost(usage, "unknown-model")
        assert cost is None


class TestCompletionsAPI:
    """Test the CompletionsAPI."""
    
    @pytest.fixture
    def api(self):
        """Create a CompletionsAPI instance."""
        registry = ModelRegistry()
        return CompletionsAPI(registry)
    
    def test_list_models(self, api):
        """Test listing models through the API."""
        models = api.list_models()
        assert len(models) > 0
        assert "gpt-4o" in models
        
        # Test with filters
        openai_models = api.list_models(provider="openai")
        assert all(api.get_model_info(m)["provider"] == "openai" for m in openai_models)
    
    def test_get_model_info(self, api):
        """Test getting model information."""
        info = api.get_model_info("gpt-4o")
        assert info is not None
        assert info["id"] == "gpt-4o"
        assert info["provider"] == "openai"
        assert "chat" in info["capabilities"]
        assert info["context_window"] > 0
        
        # Test non-existent model
        info = api.get_model_info("non-existent")
        assert info is None
    
    def test_get_usage_stats(self, api):
        """Test getting usage statistics."""
        stats = api.get_usage_stats()
        assert "total_requests" in stats
        assert "total_tokens" in stats
        assert "total_cost" in stats
        assert "requests_by_model" in stats
        assert "tokens_by_model" in stats
        assert "cost_by_model" in stats
    
    @pytest.mark.asyncio
    async def test_create_completion(self, api):
        """Test creating a completion (mocked)."""
        # Mock the model registry's complete method
        mock_response = CompletionResponse(
            id="test-id",
            model="gpt-4o",
            created=datetime.now(),
            choices=[
                CompletionChoice(
                    index=0,
                    message=Message(role=MessageRole.ASSISTANT, content="Test response"),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cost=0.0001,
            ),
        )
        
        api.model_registry.complete = AsyncMock(return_value=mock_response)
        
        # Test the API
        messages = [{"role": "user", "content": "Hello"}]
        response = await api.create(
            model="gpt-4o",
            messages=messages,
            user_id="test-user",
        )
        
        assert response == mock_response
        api.model_registry.complete.assert_called_once()


class TestGlobalInstances:
    """Test global instance getters."""
    
    def test_get_model_registry(self):
        """Test getting the global model registry."""
        registry1 = get_model_registry()
        registry2 = get_model_registry()
        assert registry1 is registry2  # Should be the same instance
    
    def test_get_completions_api(self):
        """Test getting the global completions API."""
        api1 = get_completions_api()
        api2 = get_completions_api()
        assert api1 is api2  # Should be the same instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])