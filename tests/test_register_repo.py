import os
import sys
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_register_repo(monkeypatch, capture, status=201):
    azure_mod = types.ModuleType('azure')
    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def upsert_item(self, entity):
            capture['entity'] = entity

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
        def __init__(self, headers=None):
            self.headers = headers or {}
        def get_json(self):
            return {}
    class DummyResponse:
        def __init__(self, body='', status_code=200):
            self.body = body
            self.status_code = status_code
    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    auth_mod = types.ModuleType('auth')
    def verify_token(h):
        if h == 'Bearer good':
            return 'user1'
        raise Exception('bad')
    auth_mod.verify_token = verify_token

    req_mod = types.ModuleType('requests')
    def post(url, json=None, headers=None, timeout=None):
        capture['post'] = (url, json, headers)
        return types.SimpleNamespace(status_code=status, text='', json=lambda: {'clone_url': 'http://gitea/repo.git'})
    req_mod.post = post

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'auth', auth_mod)
    monkeypatch.setitem(sys.modules, 'requests', req_mod)

    spec = importlib.util.spec_from_file_location('RegisterRepo', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'RegisterRepo', '__init__.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules['RegisterRepo'] = module
    spec.loader.exec_module(module)
    return module, DummyRequest


def test_repo_created(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['GITEA_URL'] = 'http://gitea'
    os.environ['GITEA_TOKEN'] = 'tok'
    capture = {}
    module, Req = load_register_repo(monkeypatch, capture)
    req = Req(headers={'Authorization': 'Bearer good'})
    resp = module.main(req)
    assert resp.status_code == 200
    assert capture['entity']['pk'] == 'user1'
    assert capture['post'][0] == 'http://gitea/api/v1/user/repos'
    assert capture['post'][2]['Authorization'] == 'token tok'


def test_repo_failure(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['GITEA_URL'] = 'http://gitea'
    os.environ['GITEA_TOKEN'] = 'tok'
    capture = {}
    module, Req = load_register_repo(monkeypatch, capture, status=500)
    req = Req(headers={'Authorization': 'Bearer good'})
    resp = module.main(req)
    assert resp.status_code == 500
