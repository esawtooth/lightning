import os
import sys
import json
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_user_auth(monkeypatch, store, jwt_claims=None, token_capture=None):
    azure_mod = types.ModuleType('azure')
    func_mod = types.ModuleType('functions')

    class DummyRequest:
        def __init__(self, body=None):
            self._body = body
            self.route_params = {}
            self.headers = {}

        def get_json(self):
            if self._body is None:
                raise ValueError('no body')
            return json.loads(self._body)

        def get_body(self):
            return self._body or b''

    class DummyResponse:
        def __init__(self, body='', status_code=200, mimetype=None):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype

    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def __init__(self):
            self.store = store

        def read_item(self, id, partition_key=None):
            key = (partition_key, id)
            if key not in self.store:
                raise Exception('nf')
            return self.store[key]

        def upsert_item(self, item):
            self.store[(item['pk'], item['id'])] = item

        def query_items(self, query=None, enable_cross_partition_query=False):
            return list(self.store.values())

    class DummyDatabase:
        def create_container_if_not_exists(self, *a, **k):
            return DummyContainer()

    class DummyClient:
        def create_database_if_not_exists(self, *a, **k):
            return DummyDatabase()

    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {'path': path}
    azure_mod.cosmos = cosmos_mod

    jwt_mod = types.ModuleType('jwt')

    comm_mod = types.ModuleType('communication')
    email_mod = types.ModuleType('email')

    class DummyEmailClient:
        def __init__(self, *a, **k):
            pass

        def begin_send(self, *a, **k):
            pass

    email_mod.EmailClient = DummyEmailClient
    comm_mod.email = email_mod
    azure_mod.communication = comm_mod
    monkeypatch.setitem(sys.modules, 'azure.communication', comm_mod)
    monkeypatch.setitem(sys.modules, 'azure.communication.email', email_mod)

    def encode(payload, key, algorithm=None):
        if token_capture is not None:
            token_capture['payload'] = payload
            token_capture['key'] = key
        return f"token-{payload['sub']}"

    def decode(token, key, algorithms=None):
        if jwt_claims is None:
            raise Exception('invalid')
        return jwt_claims

    jwt_mod.encode = encode
    jwt_mod.decode = decode

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)
    monkeypatch.setitem(sys.modules, 'jwt', jwt_mod)

    spec = importlib.util.spec_from_file_location(
        'UserAuth',
        os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'UserAuth', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['UserAuth'] = module
    spec.loader.exec_module(module)
    return module, DummyRequest


def test_approve_user(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['ACS_SENDER'] = 'from@example.com'
    os.environ['VERIFY_BASE_URL'] = 'http://test'
    store = {('alice', 'user'): {'pk': 'alice', 'id': 'user', 'status': 'waitlist'}}
    mod, _ = load_user_auth(monkeypatch, store)

    resp = mod._approve_user({'user_id': 'alice', 'action': 'approve'}, 'admin')
    assert resp.status_code == 200
    entity = store[('alice', 'user')]
    assert entity['status'] == 'approved'
    assert entity['approved_by'] == 'admin'
    assert entity['approved_at'] is not None


def test_reject_user(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['ACS_SENDER'] = 'from@example.com'
    os.environ['VERIFY_BASE_URL'] = 'http://test'
    store = {('bob', 'user'): {'pk': 'bob', 'id': 'user', 'status': 'waitlist'}}
    mod, _ = load_user_auth(monkeypatch, store)

    resp = mod._approve_user({'user_id': 'bob', 'action': 'reject'}, 'admin')
    assert resp.status_code == 200
    entity = store[('bob', 'user')]
    assert entity['status'] == 'rejected'


def test_list_pending_users(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['ACS_SENDER'] = 'from@example.com'
    os.environ['VERIFY_BASE_URL'] = 'http://test'
    store = {
        ('a', 'user'): {'pk': 'a', 'id': 'user', 'status': 'waitlist'},
        ('b', 'user'): {'pk': 'b', 'id': 'user', 'status': 'approved'},
        ('c', 'user'): {'pk': 'c', 'id': 'user', 'status': 'rejected'},
    }
    mod, _ = load_user_auth(monkeypatch, store)

    resp = mod._list_pending_users('admin')
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data['pending_count'] == 1
    assert data['approved_count'] == 1
    assert data['rejected_count'] == 1
    assert len(data['users']) == 3
    for u in data['users']:
        assert 'hash' not in u
        assert 'salt' not in u
        assert u['user_id'] == u['pk']


def test_approve_requires_admin(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['ACS_SENDER'] = 'from@example.com'
    os.environ['VERIFY_BASE_URL'] = 'http://test'
    store = {('d', 'user'): {'pk': 'd', 'id': 'user', 'status': 'waitlist'}}
    claims = {'sub': 'd', 'role': 'user'}
    mod, Request = load_user_auth(monkeypatch, store, jwt_claims=claims)

    req = Request(body=json.dumps({'user_id': 'd'}))
    req.route_params = {'action': 'approve'}
    req.headers['Authorization'] = 'Bearer tok'
    resp = mod.main(req)
    assert resp.status_code == 403


def test_pending_requires_admin(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ACS_CONNECTION'] = 'conn'
    os.environ['ACS_SENDER'] = 'from@example.com'
    os.environ['VERIFY_BASE_URL'] = 'http://test'
    store = {}
    claims = {'sub': 'd', 'role': 'user'}
    mod, Request = load_user_auth(monkeypatch, store, jwt_claims=claims)

    req = Request()
    req.route_params = {'action': 'pending'}
    req.headers['Authorization'] = 'Bearer tok'
    resp = mod.main(req)
    assert resp.status_code == 403
