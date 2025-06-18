import os
import sys
from datetime import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lightning_core.events.models import Event


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
    assert event.history == []
    out = event.to_dict()
    assert out["userID"] == "u1"
    assert out["history"] == []


def test_event_auto_generates_id():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "t",
        "userID": "u2",
    }
    event = Event.from_dict(data)
    assert event.id is not None
    assert event.history == []
    # id should be a 32 character hex string
    assert isinstance(event.id, str) and len(event.id) == 32
    out = event.to_dict()
    assert out["id"] == event.id
    assert out["history"] == []


def test_event_parses_z_timezone():
    data = {
        "timestamp": "2023-01-01T00:00:00Z",
        "source": "s",
        "type": "t",
        "userID": "u3",
    }
    event = Event.from_dict(data)
    assert event.timestamp.isoformat() == "2023-01-01T00:00:00+00:00"
    assert event.history == []


def test_event_invalid_timestamp(monkeypatch):
    data = {
        'timestamp': 'bad',
        'source': 's',
        'type': 't',
        'userID': 'u',
    }
    with pytest.raises(ValueError):
        Event.from_dict(data)


def test_event_numeric_timestamp(monkeypatch):
    ts = int(datetime.now().timestamp())
    data = {
        'timestamp': ts,
        'source': 's',
        'type': 't',
        'userID': 'u',
    }
    event = Event.from_dict(data)
    assert int(event.timestamp.timestamp()) == ts
    assert event.history == []


def test_event_history_not_list(monkeypatch):
    data = {
        'timestamp': datetime.now().isoformat(),
        'source': 's',
        'type': 't',
        'userID': 'u',
        'history': {},
    }
    with pytest.raises(ValueError):
        Event.from_dict(data)
