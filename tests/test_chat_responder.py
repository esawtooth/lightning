import os
import sys
import json
import types
import asyncio
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from events import LLMChatEvent


def load_chat_agent(monkeypatch, capture):
    openai_stub = types.ModuleType("openai")

    class ChatStub:
        @staticmethod
        def create(messages=None, model=None, **kwargs):
            capture["model"] = model
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 7},
            }

    openai_stub.ChatCompletion = ChatStub
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    model_registry = types.SimpleNamespace(
        get_model=lambda mid: types.SimpleNamespace(id=mid),
        get_cheapest_model=lambda capability: types.SimpleNamespace(id="cheap"),
    )
    monkeypatch.setattr(
        "vextir_os.core_drivers.get_model_registry", lambda: model_registry
    )

    from vextir_os.core_drivers import ChatAgentDriver

    return ChatAgentDriver(ChatAgentDriver._vextir_manifest)


def test_openai_model_env(monkeypatch):
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["OPENAI_API_KEY"] = "sk-test"

    captured = {}
    driver = load_chat_agent(monkeypatch, captured)

    event = {
        "timestamp": "2023-01-01T00:00:00Z",
        "source": "test",
        "type": "llm.chat",
        "userID": "u",
        "metadata": {"messages": [{"role": "user", "content": "hi"}]},
    }
    llm_event = LLMChatEvent.from_dict(event)
    results = asyncio.run(driver.handle_event(llm_event))

    assert captured["model"] == "test-model"
    assert results[0].metadata["usage"]["total_tokens"] == 7


def test_missing_api_key(monkeypatch):
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]

    captured = {}
    driver = load_chat_agent(monkeypatch, captured)

    event = {
        "timestamp": "2023-01-01T00:00:00Z",
        "source": "test",
        "type": "llm.chat",
        "userID": "u",
        "metadata": {"messages": [{"role": "user", "content": "hi"}]},
    }
    llm_event = LLMChatEvent.from_dict(event)
    results = asyncio.run(driver.handle_event(llm_event))

    assert results[0].type == "llm.chat.response"
