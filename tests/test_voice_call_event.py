from datetime import datetime
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lightning_core.events.models import VoiceCallEvent


def test_voice_call_missing_phone():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "voice.call",
        "userID": "u1",
        "metadata": {},
    }
    with pytest.raises(ValueError):
        VoiceCallEvent.from_dict(data)


def test_voice_call_round_trip():
    now = datetime.now()
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "voice.call",
        "userID": "u1",
        "metadata": {"phone": "+123", "objective": "say hi"},
    }
    event = VoiceCallEvent.from_dict(data)
    assert event.phone == "+123"
    assert event.objective == "say hi"
    out = event.to_dict()
    assert out["metadata"]["phone"] == "+123"
    assert out["metadata"]["objective"] == "say hi"
