import os
import sys
import json
import types
import importlib.util
import hashlib

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

    class DummyResponse:
        def __init__(self, body='', status_code=200, mimetype=None):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype

    func_mod.HttpRequest = DummyRequest
    func_mod.HttpResponse = DummyResponse
    azure_mod.functions = func_mod

    tables_mod = types.ModuleType('tables')

    class DummyTable:
        def __init__(self):
            self.store = store

        def create_table_if_not_exists(self):
            pass

        def get_entity(self, pk, rk):
            key = (pk, rk)
            if key not in self.store:
                raise Exception('nf')
            return self.store[key]

        def upsert_entity(self, ent):
            self.store[(ent['PartitionKey'], ent['RowKey'])] = ent

    class DummyService:
        def get_table_client(self, name):
            return DummyTable()

    tables_mod.TableServiceClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyService()
    )
    azure_mod.data = types.SimpleNamespace(tables=tables_mod)

    jwt_mod = types.ModuleType('jwt')

    def encode(payload, key, algorithm=None):
        token_capture['payload'] = payload
        token_capture['key'] = key
        return f"token-{payload['sub']}"

    jwt_mod.encode = encode

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.data.tables', tables_mod)
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
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['USER_TABLE'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    store = {}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'alice', 'password': 'pw'}))
    req.route_params = {'action': 'register'}
    resp = mod.main(req)
    assert resp.status_code == 201
    assert ('alice', 'user') in store
    assert store[('alice', 'user')]['hash'] != 'pw'


def test_register_duplicate(monkeypatch):
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['USER_TABLE'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = 's'
    store = {('bob', 'user'): {'PartitionKey': 'bob', 'RowKey': 'user', 'salt': salt, 'hash': hashlib.sha256((salt + 'pw').encode()).hexdigest()}}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'pw'}))
    req.route_params = {'action': 'register'}
    resp = mod.main(req)
    assert resp.status_code == 409


def test_login_success(monkeypatch):
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['USER_TABLE'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = 's'
    hashed = hashlib.sha256((salt + 'pw').encode()).hexdigest()
    store = {('bob', 'user'): {'PartitionKey': 'bob', 'RowKey': 'user', 'salt': salt, 'hash': hashed}}
    capture = {}
    mod, Request = load_user_auth(monkeypatch, store, capture)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'pw'}))
    req.route_params = {'action': 'login'}
    resp = mod.main(req)
    assert resp.status_code == 200
    assert json.loads(resp.body)['token'] == 'token-bob'
    assert capture['key'] == 'k'
    assert capture['payload']['sub'] == 'bob'


def test_login_bad_password(monkeypatch):
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['USER_TABLE'] = 'users'
    os.environ['JWT_SIGNING_KEY'] = 'k'
    salt = 's'
    hashed = hashlib.sha256((salt + 'pw').encode()).hexdigest()
    store = {('bob', 'user'): {'PartitionKey': 'bob', 'RowKey': 'user', 'salt': salt, 'hash': hashed}}
    cap = {}
    mod, Request = load_user_auth(monkeypatch, store, cap)

    req = Request(body=json.dumps({'username': 'bob', 'password': 'bad'}))
    req.route_params = {'action': 'login'}
    resp = mod.main(req)
    assert resp.status_code == 401

