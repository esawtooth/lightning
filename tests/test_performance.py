import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lightning_core.events.models import Event, WorkerTaskEvent
from events import utils

sample_event = {
    "timestamp": datetime.utcnow().isoformat(),
    "source": "client",
    "type": "llm.chat",
    "userID": "u123",
    "metadata": {
        "messages": [{"role": "user", "content": "hello"}],
        "commands": ["echo hi"],
        "task": "say hi",
    },
}


def test_event_from_dict_benchmark(benchmark):
    benchmark(Event.from_dict, sample_event)


def test_worker_task_from_dict_benchmark(benchmark):
    benchmark(WorkerTaskEvent.from_dict, sample_event)


def test_event_to_dict_benchmark(benchmark):
    event = Event.from_dict(sample_event)
    benchmark(event.to_dict)


def test_event_matches_benchmark(benchmark):
    benchmark(utils.event_matches, "foo.bar.baz", "foo.*")
