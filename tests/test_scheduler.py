import os
import sys
import json
import types
import asyncio
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

from events import Event
from vextir_os.orchestration_drivers import SchedulerDriver


def load_scheduler_driver(monkeypatch, capture, schedules=None):
    class DummyContainer:
        def __init__(self):
            pass

        def create_item(self, item):
            capture["entity"] = item

        def query_items(self, *a, **k):
            return schedules or []

        def upsert_item(self, e):
            capture.setdefault("updated", []).append(e)

        def delete_item(self, id, partition_key=None):
            capture.setdefault("deleted", []).append((partition_key, id))

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

    cron_mod = types.ModuleType("croniter")
    cron_mod.croniter = lambda expr, start: types.SimpleNamespace(get_next=lambda typ: start + timedelta(minutes=5))
    monkeypatch.setitem(sys.modules, "croniter", cron_mod)

    return SchedulerDriver(SchedulerDriver._vextir_manifest)


def test_schedule_creation(monkeypatch):
    os.environ["COSMOS_CONNECTION"] = "c"
    os.environ["SCHEDULE_CONTAINER"] = "t"
    capture = {}
    driver = load_scheduler_driver(monkeypatch, capture)

    event = Event(
        timestamp=datetime.utcnow(),
        source="s",
        type="schedule.create",
        user_id="u1",
        metadata={"cron": "0 0 * * *", "event": {"type": "ping"}},
    )

    results = asyncio.run(driver.handle_event(event))
    assert results[0].type == "schedule.created"
    assert capture["entity"]["pk"] == "u1"


def test_schedule_creation_no_cosmos(monkeypatch):
    if "COSMOS_CONNECTION" in os.environ:
        del os.environ["COSMOS_CONNECTION"]
    capture = {}
    driver = load_scheduler_driver(monkeypatch, capture)

    event = Event(
        timestamp=datetime.utcnow(),
        source="s",
        type="schedule.create",
        user_id="u1",
        metadata={"cron": "* * * * *", "event": {"type": "ping"}},
    )

    results = asyncio.run(driver.handle_event(event))
    assert results[0].metadata["schedule_id"] == "unknown"


def test_trigger_publishes_event(monkeypatch):
    os.environ["COSMOS_CONNECTION"] = "c"
    os.environ["SCHEDULE_CONTAINER"] = "t"

    event_template = {
        "type": "t",
        "metadata": {},
    }
    schedules = [
        {
            "pk": "u1",
            "id": "1",
            "event_template": event_template,
            "next_trigger": (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
            "cron": "",
            "enabled": True,
        }
    ]
    capture = {}
    driver = load_scheduler_driver(monkeypatch, capture, schedules)

    trigger_event = Event(
        timestamp=datetime.utcnow(),
        source="system",
        type="schedule.trigger",
        user_id="system",
        metadata={},
    )

    results = asyncio.run(driver.handle_event(trigger_event))
    assert results[0].type == "t"
    assert capture["updated"][0]["pk"] == "u1"
