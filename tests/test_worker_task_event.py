import os, sys
from datetime import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from events import WorkerTaskEvent


def test_worker_task_missing_commands():
    data = {
        "timestamp": datetime.now().isoformat(),
        "source": "s",
        "type": "worker.task",
        "userID": "u1",
        "metadata": {},
    }
    with pytest.raises(ValueError):
        WorkerTaskEvent.from_dict(data)


def test_worker_task_round_trip():
    now = datetime.now()
    cmds = ["echo hi"]
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "worker.task",
        "userID": "u1",
        "metadata": {"commands": cmds, "repo_url": "https://example.com/repo.git"},
    }
    event = WorkerTaskEvent.from_dict(data)
    assert event.commands == cmds
    assert event.repo_url == "https://example.com/repo.git"
    assert event.history == []
    out = event.to_dict()
    assert out["metadata"]["commands"] == cmds
    assert out["metadata"]["repo_url"] == "https://example.com/repo.git"
    assert out["history"] == []


def test_worker_task_with_task():
    now = datetime.now()
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "worker.task",
        "userID": "u1",
        "metadata": {"task": "run tests"},
    }
    event = WorkerTaskEvent.from_dict(data)
    assert event.task == "run tests"
    out = event.to_dict()
    assert out["metadata"]["task"] == "run tests"


def test_worker_task_with_cost():
    now = datetime.now()
    data = {
        "timestamp": now.isoformat(),
        "source": "s",
        "type": "worker.task",
        "userID": "u1",
        "metadata": {"commands": ["echo"], "cost": {"cost": 0.5, "tokens": 5}},
    }
    event = WorkerTaskEvent.from_dict(data)
    assert event.cost["cost"] == 0.5
    out = event.to_dict()
    assert out["metadata"]["cost"]["tokens"] == 5
