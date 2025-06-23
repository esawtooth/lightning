import os
import sys
import json
import types
import asyncio
from datetime import datetime
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lightning_core.events.models import Event, WorkerTaskEvent


def load_task_monitor_driver(monkeypatch, capture):
    class DummyContainer:
        def query_items(self, *a, **k):
            capture["query"] = True
            return [{"status": "started", "count": 1}]

        def read_item(self, item, partition_key=None):
            if item == "t1":
                return {"id": "t1", "pk": "u1", "container_group": "cg"}
            raise Exception("not found")

        def create_item(self, item):
            capture["created"] = item

        def upsert_item(self, item):
            capture.setdefault("upserted", []).append(item)

    class DummyDatabase:
        def create_container_if_not_exists(self, *a, **k):
            return DummyContainer()

    class DummyClient:
        def create_database_if_not_exists(self, *a, **k):
            return DummyDatabase()

    cosmos_mod = types.ModuleType("cosmos")
    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {"path": path}
    monkeypatch.setitem(sys.modules, "azure.cosmos", cosmos_mod)
    monkeypatch.setattr("vextir_os.orchestration_drivers.CosmosClient", cosmos_mod.CosmosClient)
    monkeypatch.setattr("vextir_os.orchestration_drivers.PartitionKey", cosmos_mod.PartitionKey)

    aci_mod = types.ModuleType("containerinstance")

    class DummyLogs:
        def __init__(self):
            self.content = "log"

    class DummyACI:
        class containers:
            @staticmethod
            def list_logs(rg, group, container_name):
                capture["logs"] = (rg, group, container_name)
                return DummyLogs()

    aci_mod.ContainerInstanceManagementClient = DummyACI
    monkeypatch.setitem(sys.modules, "azure.mgmt.containerinstance", aci_mod)

    from lightning_core.vextir_os.orchestration_drivers import TaskMonitorDriver

    return TaskMonitorDriver(TaskMonitorDriver._vextir_manifest)


def test_task_creation(monkeypatch):
    os.environ["COSMOS_CONNECTION"] = "c"
    capture = {}
    driver = load_task_monitor_driver(monkeypatch, capture)

    task_event = WorkerTaskEvent(
        timestamp=datetime.utcnow(),
        source="test",
        type="worker.task",
        user_id="u1",
        task="do something",
        metadata={},
    )

    results = asyncio.run(driver.handle_event(task_event))
    assert results[0].type == "task.created"
    assert capture["created"]["pk"] == "u1"


def test_task_metrics(monkeypatch):
    os.environ["COSMOS_CONNECTION"] = "c"
    capture = {}
    driver = load_task_monitor_driver(monkeypatch, capture)

    metrics_event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="task.metrics.request",
        user_id="u1",
        metadata={},
    )

    results = asyncio.run(driver.handle_event(metrics_event))
    assert results[0].type == "task.metrics.response"
    assert capture["query"] is True
