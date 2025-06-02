import os
import sys
import json
import importlib
import types
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from events import WorkerTaskEvent


def test_worker_main_runs_agent(monkeypatch, capsys):
    # create a dummy agent
    from agents import AGENT_REGISTRY, Agent

    class DummyAgent(Agent):
        name = "openai-shell"

        def run(self, commands):
            assert commands == "do stuff"
            self.last_usage = {"total_tokens": 100}
            return "ok"

    AGENT_REGISTRY["openai-shell"] = DummyAgent()

    # stub cosmos client
    cosmos_mod = types.ModuleType("cosmos")

    class DummyContainer:
        def __init__(self):
            self.updated = None

        def create_container_if_not_exists(self, *a, **k):
            return self

        def create_database_if_not_exists(self, *a, **k):
            return self

        def upsert_item(self, item):
            self.updated = item

        def read_item(self, item, partition_key=None):
            return {}

    dummy_container = DummyContainer()
    cosmos_mod.CosmosClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: dummy_container
    )
    cosmos_mod.PartitionKey = lambda path: {"path": path}
    monkeypatch.setitem(sys.modules, "azure.cosmos", cosmos_mod)
    os.environ["COSMOS_CONNECTION"] = "conn"
    os.environ["COSMOS_DATABASE"] = "db"
    os.environ["TASK_CONTAINER"] = "tasks"
    os.environ["TASK_ID"] = "t1"

    event = WorkerTaskEvent(
        timestamp=datetime.utcnow(),
        source="t",
        type="worker.task",
        user_id="u1",
        metadata={},
        task="do stuff",
    )
    os.environ["WORKER_EVENT"] = json.dumps(event.to_dict())

    module = importlib.import_module("worker")
    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ok" in captured.out
    assert abs(dummy_container.updated["cost"] - 0.0002) < 1e-6
