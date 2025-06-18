import os
import sys
import json
import importlib
import types
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lightning_core.events.models import WorkerTaskEvent


def test_worker_main_runs_agent(monkeypatch, capsys):
    # create a dummy agent
    from agents import AGENT_REGISTRY, Agent

    class DummyAgent(Agent):
        name = "conseil"

        def run(self, commands):
            assert commands == "do stuff"
            self.last_usage = {"total_tokens": 100}
            return "ok"

    AGENT_REGISTRY["conseil"] = DummyAgent()

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
    info = dummy_container.updated["cost"]
    assert abs(info["cost"] - 0.0002) < 1e-6
    assert info["tokens"] == 100
    assert info["event_count"] == 1
    assert info["runtime_sec"] >= 0


def load_worker_task_runner(monkeypatch, capture):
    azure_mod = types.ModuleType("azure")

    cosmos_mod = types.ModuleType("cosmos")

    class DummyContainer:
        def create_container_if_not_exists(self, *a, **k):
            return self

        def create_database_if_not_exists(self, *a, **k):
            return self

        def upsert_item(self, item):
            capture.setdefault("upserts", []).append(item)

        def read_item(self, item, partition_key=None):
            return {"repo": "r"}

    cosmos_mod.CosmosClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyContainer()
    )
    cosmos_mod.PartitionKey = lambda path: {"path": path}
    azure_mod.cosmos = cosmos_mod

    sb_mod = types.ModuleType("servicebus")

    class DummySender:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def send_messages(self, msg):
            capture["sent"] = json.loads(msg.body)

    class DummySBClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def get_queue_sender(self, queue_name=None):
            return DummySender()

    sb_mod.ServiceBusClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummySBClient()
    )

    class DummyMessage:
        def __init__(self, body):
            self.body = body
            self.application_properties = {}

    sb_mod.ServiceBusMessage = DummyMessage
    azure_mod.servicebus = sb_mod

    func_mod = types.ModuleType("functions")

    class SBMessage:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def get_body(self):
            return self._body

    func_mod.ServiceBusMessage = SBMessage
    azure_mod.functions = func_mod

    identity_mod = types.ModuleType("identity")
    identity_mod.DefaultAzureCredential = lambda: None
    azure_mod.identity = identity_mod

    aci_mod = types.ModuleType("containerinstance")

    class DummyGroups:
        def begin_create_or_update(self, rg, name, group):
            capture["created"] = name
            return types.SimpleNamespace(result=lambda: None)

        def begin_delete(self, rg, name):
            capture["deleted"] = name

    class DummyACIClient:
        def __init__(self, credential, sub_id):
            self.container_groups = DummyGroups()

    aci_mod.ContainerInstanceManagementClient = DummyACIClient

    models_mod = types.ModuleType("containerinstance.models")

    class Container:
        def __init__(self, *a, **k):
            pass

    class ContainerGroup:
        def __init__(self, *a, **k):
            pass

    class ContainerGroupRestartPolicy:
        NEVER = "never"

    class EnvironmentVariable:
        def __init__(self, name=None, value=None):
            self.name = name
            self.value = value

    class OperatingSystemTypes:
        LINUX = "linux"

    class ResourceRequests:
        def __init__(self, cpu=None, memory_in_gb=None):
            pass

    class ResourceRequirements:
        def __init__(self, requests=None):
            pass

    models_mod.Container = Container
    models_mod.ContainerGroup = ContainerGroup
    models_mod.ContainerGroupRestartPolicy = ContainerGroupRestartPolicy
    models_mod.EnvironmentVariable = EnvironmentVariable
    models_mod.OperatingSystemTypes = OperatingSystemTypes
    models_mod.ResourceRequests = ResourceRequests
    models_mod.ResourceRequirements = ResourceRequirements

    azure_mod.mgmt = types.ModuleType("mgmt")
    azure_mod.mgmt.containerinstance = aci_mod
    aci_mod.models = models_mod

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.cosmos", cosmos_mod)
    monkeypatch.setitem(sys.modules, "azure.servicebus", sb_mod)
    monkeypatch.setitem(sys.modules, "azure.functions", func_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", identity_mod)
    monkeypatch.setitem(sys.modules, "azure.mgmt.containerinstance", aci_mod)
    monkeypatch.setitem(
        sys.modules, "azure.mgmt.containerinstance.models", models_mod
    )

    spec = importlib.util.spec_from_file_location(
        "WorkerTaskRunner",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "azure-function",
            "WorkerTaskRunner",
            "__init__.py",
        ),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["WorkerTaskRunner"] = module
    spec.loader.exec_module(module)
    return module, SBMessage


def test_cleanup_invoked(monkeypatch):
    os.environ["COSMOS_CONNECTION"] = "c"
    os.environ["COSMOS_DATABASE"] = "db"
    os.environ["REPO_CONTAINER"] = "r"
    os.environ["TASK_CONTAINER"] = "t"
    os.environ["SERVICEBUS_CONNECTION"] = "sb"
    os.environ["SERVICEBUS_QUEUE"] = "q"
    os.environ["ACI_RESOURCE_GROUP"] = "rg"
    os.environ["ACI_SUBSCRIPTION_ID"] = "sub"

    capture = {}
    module, SBMessage = load_worker_task_runner(monkeypatch, capture)

    event = WorkerTaskEvent(
        timestamp=datetime.utcnow(),
        source="t",
        type="worker.task",
        user_id="u",
        metadata={"commands": ["echo"], "repo_url": "http://repo"},
    )
    msg = SBMessage(json.dumps(event.to_dict()))
    module.main(msg)

    assert capture.get("deleted") == capture.get("created")
