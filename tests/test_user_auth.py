import os
import sys
import json
import types
import importlib.util
import crypt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_user_auth(monkeypatch, store, token_capture):
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

    def encode(payload, key, algorithm=None):
        token_capture['payload'] = payload
        token_capture['key'] = key
        return f"token-{payload['sub']}"

    def decode(token, key, algorithms=None):
        if not token.startswith('token-'):
            raise Exception('bad token')
        sub = token.split('-', 1)[1]
        return {'sub': sub, 'role': 'user', 'status': 'approved', 'exp': 0}

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


def test_register_success(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    store = {}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'alice', 'password': 'Password1'}))
    req.route_params = {'action': 'register'}
    resp = mod.main(req)
    assert resp.status_code == 201
    assert ('alice', 'user') in store
    assert store[('alice', 'user')]['hash'] != 'Password1'


def test_register_duplicate(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = '$2b$12$abcdefghijklmnopqrstuv'
    store = {('bob', 'user'): {'pk': 'bob', 'id': 'user', 'salt': salt, 'hash': crypt.crypt('pw', salt)}}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'Password1'}))
    req.route_params = {'action': 'register'}
    resp = mod.main(req)
    assert resp.status_code == 409


def test_login_success(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = '$2b$12$abcdefghijklmnopqrstuv'
    hashed = crypt.crypt('pw', salt)
    store = {('bob', 'user'): {'pk': 'bob', 'id': 'user', 'salt': salt, 'hash': hashed}}
    capture = {}
    mod, Request = load_user_auth(monkeypatch, store, capture)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'Password1'}))
    req.route_params = {'action': 'login'}
    resp = mod.main(req)
    assert resp.status_code == 200
    assert json.loads(resp.body)['token'] == 'token-bob'
    assert capture['key'] == 'k'
    assert capture['payload']['sub'] == 'bob'


def test_login_bad_password(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = '$2b$12$abcdefghijklmnopqrstuv'
    hashed = crypt.crypt('pw', salt)
    store = {('bob', 'user'): {'pk': 'bob', 'id': 'user', 'salt': salt, 'hash': hashed}}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'bad'}))
    req.route_params = {'action': 'login'}
    resp = mod.main(req)
    assert resp.status_code == 401


def test_register_weak_password(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    store = {}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'weak', 'password': 'short'}))
    req.route_params = {'action': 'register'}
    resp = mod.main(req)
    assert resp.status_code == 400


def test_refresh_success(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    store = {}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request()
    req.route_params = {'action': 'refresh'}
    req.headers = {'Authorization': 'Bearer token-alice'}
    resp = mod.main(req)
    assert resp.status_code == 200
    assert json.loads(resp.body)['token'] == 'token-alice'


def test_refresh_invalid_token(monkeypatch):
    os.environ['COSMOS_CONNECTION'] = 'c'
    os.environ['USER_CONTAINER'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    store = {}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request()
    req.route_params = {'action': 'refresh'}
    req.headers = {'Authorization': 'Bearer bad'}
    resp = mod.main(req)
    assert resp.status_code == 401

