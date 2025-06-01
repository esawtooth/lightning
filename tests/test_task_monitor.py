import os
import sys
import json
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_task_monitor(monkeypatch, capture):
    azure_mod = types.ModuleType('azure')

    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def query_items(self, *a, **k):
            capture['query'] = True
            return [{"id": "t1", "pk": "u1", "status": "started"}]

        def read_item(self, item, partition_key=None):
            if item == 't1':
                return {"id": "t1", "pk": "u1", "container_group": "cg"}
            raise Exception('not found')

    class DummyDatabase:
        def create_container_if_not_exists(self, *a, **k):
            return DummyContainer()

    class DummyClient:
        def create_database_if_not_exists(self, *a, **k):
            return DummyDatabase()

    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {'path': path}
    azure_mod.cosmos = cosmos_mod

    aci_mod = types.ModuleType('containerinstance')

    class DummyLogs:
        def __init__(self):
            self.content = 'log'

    class DummyACI:
        def __init__(self, *a, **k):
            pass
        class containers:
            @staticmethod
            def list_logs(rg, group, container_name):
                capture['logs'] = (rg, group, container_name)
                return DummyLogs()

    aci_mod.ContainerInstanceManagementClient = DummyACI
    azure_mod.mgmt = types.SimpleNamespace(containerinstance=aci_mod)

    identity_mod = types.ModuleType('identity')
    identity_mod.DefaultAzureCredential = lambda *a, **k: None
    azure_mod.identity = identity_mod

    auth_mod = types.ModuleType('auth')

    def verify_token(header):
        if header == 'Bearer good':
            return 'u1'
        raise Exception('bad')

    auth_mod.verify_token = verify_token

    func_mod = types.ModuleType('functions')

    class DummyRequest:
        def __init__(self, route_params=None, headers=None):
            self.route_params = route_params or {}
            self.headers = headers or {}

    class DummyResponse:
        def __init__(self, body='', status_code=200, mimetype=None):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype

    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)
    monkeypatch.setitem(sys.modules, 'azure.mgmt.containerinstance', aci_mod)
    monkeypatch.setitem(sys.modules, 'azure.identity', identity_mod)
    monkeypatch.setitem(sys.modules, 'auth', auth_mod)

    spec = importlib.util.spec_from_file_location(
        'TaskMonitor', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'TaskMonitor', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['TaskMonitor'] = module
    spec.loader.exec_module(module)
    return module, DummyRequest


def test_task_list(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['ACI_RESOURCE_GROUP'] = 'g'
    os.environ['ACI_SUBSCRIPTION_ID'] = 's'
    capture = {}
    module, Request = load_task_monitor(monkeypatch, capture)
    req = Request(headers={'Authorization': 'Bearer good'})
    resp = module.main(req)
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data[0]['id'] == 't1'


def test_task_logs(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['ACI_RESOURCE_GROUP'] = 'g'
    os.environ['ACI_SUBSCRIPTION_ID'] = 's'
    capture = {}
    module, Request = load_task_monitor(monkeypatch, capture)
    req = Request(route_params={'task_id': 't1'}, headers={'Authorization': 'Bearer good'})
    resp = module.main(req)
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data['id'] == 't1'
    assert data['logs'] == 'log'
    assert capture['logs'] == ('g', 'cg', 'worker')
