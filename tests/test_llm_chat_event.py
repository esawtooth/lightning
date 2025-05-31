import os
import sys
from datetime import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from events import LLMChatEvent


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
    out = event.to_dict()
    assert out["metadata"]["messages"] == msgs
