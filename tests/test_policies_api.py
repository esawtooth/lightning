import sys
import json
import types
import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def load_policy_api(monkeypatch, store, token_map=None):
    azure_mod = types.ModuleType('azure')
    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def __init__(self):
            self.store = store
        def upsert_item(self, item):
            self.store[(item['pk'], item['id'])] = item
        def read_item(self, id, partition_key=None):
            key = (partition_key, id)
            if key not in self.store:
                raise Exception('nf')
            return self.store[key]

    class DummyDatabase:
        def create_container_if_not_exists(self, *a, **k):
            return DummyContainer()

    class DummyClient:
        def create_database_if_not_exists(self, *a, **k):
            return DummyDatabase()

    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {'path': path}
    azure_mod.cosmos = cosmos_mod

    func_mod = types.ModuleType('functions')
    class DummyRequest:
        def __init__(self, method='GET', body=None, headers=None, route_params=None):
            self.method = method
            self._body = body
            self.headers = headers or {}
            self.route_params = route_params or {}
        def get_json(self):
            if self._body is None:
                raise ValueError('no body')
            return json.loads(self._body)
    class DummyResponse:
        def __init__(self, body='', status_code=200, mimetype=None):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype
    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    auth_mod = types.ModuleType('auth')
    token_map = token_map or {'Bearer good': 'u1'}
    def verify_token(header):
        if header in token_map:
            return token_map[header]
        raise Exception('bad')
    auth_mod.verify_token = verify_token

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)
    monkeypatch.setitem(sys.modules, 'auth', auth_mod)

    spec = importlib.util.spec_from_file_location(
        'PolicyManager', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'PolicyManager', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['PolicyManager'] = module
    spec.loader.exec_module(module)
    return module, DummyRequest

def test_get_policy(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    store = {('u1', 'policy'): {'id': 'policy', 'pk': 'u1', 'policy': {'prompt': 'hi'}}}
    mod, Request = load_policy_api(monkeypatch, store)
    req = Request(method='GET', headers={'Authorization': 'Bearer good'})
    resp = mod.main(req)
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data['prompt'] == 'hi'


def test_update_policy(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    store = {}
    mod, Request = load_policy_api(monkeypatch, store)
    body = json.dumps({'prompt': 'new', 'blocked_patterns': ['curl']})
    req = Request(method='PUT', body=body, headers={'Authorization': 'Bearer good'})
    resp = mod.main(req)
    assert resp.status_code == 200
    assert ('u1', 'policy') in store
    assert store[('u1', 'policy')]['policy']['prompt'] == 'new'
