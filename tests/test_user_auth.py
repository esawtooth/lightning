import os
import sys
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_user_auth(monkeypatch, capture):
    azure_mod = types.ModuleType('azure')

    # cosmos stub
    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def __init__(self):
            self.items = []
        def upsert_item(self, item):
            found = False
            for i, it in enumerate(self.items):
                if it['pk'] == item['pk']:
                    self.items[i] = item
                    found = True
                    break
            if not found:
                self.items.append(item)
        def query_items(self, query=None, parameters=None, enable_cross_partition_query=None):
            token = parameters[0]['value']
            return [i for i in self.items if i.get('verify_token') == token]

    class DummyDatabase:
        def __init__(self):
            self.container = DummyContainer()
        def create_container_if_not_exists(self, *a, **k):
            return self.container

    class DummyClient:
        def __init__(self):
            self.db = DummyDatabase()
        def create_database_if_not_exists(self, *a, **k):
            return self.db

    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {'path': path}
    azure_mod.cosmos = cosmos_mod

    # functions stub
    func_mod = types.ModuleType('functions')

    class DummyRequest:
        def __init__(self, method='GET', body=None, params=None, route_params=None):
            self.method = method
            self._body = body or {}
            self.params = params or {}
            self.route_params = route_params or {}
        def get_json(self):
            return self._body
    class DummyResponse:
        def __init__(self, body='', status_code=200):
            self.body = body
            self.status_code = status_code
    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    # email stub
    comm_mod = types.ModuleType('communication')
    email_mod = types.ModuleType('email')
    class DummyEmailClient:
        def __init__(self, conn):
            capture['conn'] = conn
        def begin_send(self, message):
            capture['message'] = message
    email_mod.EmailClient = DummyEmailClient
    email_mod.EmailClient.from_connection_string = classmethod(lambda cls, conn: cls(conn))
    comm_mod.email = email_mod
    azure_mod.communication = comm_mod

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)
    monkeypatch.setitem(sys.modules, 'azure.communication.email', email_mod)

    spec = importlib.util.spec_from_file_location('UserAuth', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'UserAuth', '__init__.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules['UserAuth'] = module
    spec.loader.exec_module(module)
    return module, DummyRequest, DummyResponse


def test_registration_sends_email_and_verifies(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['VERIFY_BASE_URL'] = 'http://host'
    os.environ['ACS_SENDER'] = 'noreply@test.com'
    capture = {}

    module, Req, Resp = load_user_auth(monkeypatch, capture)

    req = Req(method='POST', body={'username': 'u', 'password': 'pw', 'email': 'e@test.com'}, route_params={'action': 'register'})
    resp = module.main(req)
    assert resp.status_code == 201
    assert capture['message']['senderAddress'] == 'noreply@test.com'
    token = module._container.items[0]['verify_token']
    assert token in capture['message']['content']['plainText']

    req2 = Req(method='GET', params={'token': token}, route_params={'action': 'verify'})
    resp2 = module.main(req2)
    assert resp2.status_code == 200
    assert module._container.items[0]['email_verified']
