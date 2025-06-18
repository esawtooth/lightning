import os
import sys
from datetime import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lightning_core.events.models import LLMChatEvent


def test_llmchat_missing_messages():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "llm.chat",
        "userID": "u1",
        "metadata": {},
    }
    with pytest.raises(ValueError):
        LLMChatEvent.from_dict(data)


def test_llmchat_invalid_messages_type():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "llm.chat",
        "userID": "u1",
        "metadata": {"messages": "notalist"},
    }
    with pytest.raises(ValueError):
        LLMChatEvent.from_dict(data)


def test_llmchat_message_missing_role():
    now = datetime.now()
    msgs = [{"content": "hi"}]
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "llm.chat",
        "userID": "u1",
        "metadata": {"messages": msgs},
    }
    with pytest.raises(ValueError):
        LLMChatEvent.from_dict(data)


def test_llmchat_message_missing_content():
    now = datetime.now()
    msgs = [{"role": "user"}]
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "llm.chat",
        "userID": "u1",
        "metadata": {"messages": msgs},
    }
    with pytest.raises(ValueError):
        LLMChatEvent.from_dict(data)


def test_llmchat_round_trip():
    now = datetime.now()
    msgs = [{"role": "user", "content": "hi"}]
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "llm.chat",
        "userID": "u1",
        "metadata": {"messages": msgs},
    }
    event = LLMChatEvent.from_dict(data)
    assert event.messages == msgs
    assert event.history == []
    out = event.to_dict()
    assert out["metadata"]["messages"] == msgs
    assert out["history"] == []
