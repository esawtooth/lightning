import os
import sys
import json
import importlib
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from events import WorkerTaskEvent


def test_worker_main_runs_agent(monkeypatch, capsys):
    # create a dummy agent
    from agents import AGENT_REGISTRY, Agent

    class DummyAgent(Agent):
        name = "openai-shell"
        def run(self, commands):
            assert commands == "do stuff"
            return "ok"

    AGENT_REGISTRY["openai-shell"] = DummyAgent()

    event = WorkerTaskEvent(
        timestamp=datetime.utcnow(),
        source="t",
        type="worker.task",
        user_id="u1",
        metadata={},
        task="do stuff"
    )
    os.environ["WORKER_EVENT"] = json.dumps(event.to_dict())

    module = importlib.import_module("worker")
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ok" in captured.out


def test_worker_main_policy_violation(monkeypatch, capsys):
    from agents import AGENT_REGISTRY, Agent
    from policy import PolicyViolationError

    class BadAgent(Agent):
        name = "openai-shell"
        def run(self, commands):
            raise PolicyViolationError("blocked")

    AGENT_REGISTRY["openai-shell"] = BadAgent()

    event = WorkerTaskEvent(
        timestamp=datetime.utcnow(),
        source="t",
        type="worker.task",
        user_id="u1",
        metadata={},
        task="oops",
    )
    os.environ["WORKER_EVENT"] = json.dumps(event.to_dict())

    module = importlib.import_module("worker")
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Policy violation" in captured.err


