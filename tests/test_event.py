import os
import sys
from datetime import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from events import Event


def test_event_requires_userid():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "t",
    }
    with pytest.raises(ValueError):
        Event.from_dict(data)


def test_event_round_trip():
    now = datetime.now()
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "t",
        "userID": "u1",
        "metadata": {"a": 1},
    }
    event = Event.from_dict(data)
    assert event.user_id == "u1"
    out = event.to_dict()
    assert out["userID"] == "u1"
