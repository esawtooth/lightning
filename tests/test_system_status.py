import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from events.eventgen.laptop.linux import system_status
from events import Event


def test_collect_events():
    events = system_status.collect_events(user_id="tester")
    assert isinstance(events, list) and events
    assert all(isinstance(e, Event) for e in events)
    types = {e.type for e in events}
    # CPU and memory events should always be present
    assert "laptop.cpu" in types
    assert "laptop.memory" in types
