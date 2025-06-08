import os
import sys
import types
import importlib.util

from fastapi.testclient import TestClient


def load_gateway_app(monkeypatch, capture, with_url=True):
    # Dummy FastAPI app for auth and chat
    from fastapi import FastAPI
    dummy = FastAPI()
    monkeypatch.setitem(sys.modules, 'auth_app', types.SimpleNamespace(app=dummy))
    monkeypatch.setitem(sys.modules, 'chainlit_app', types.SimpleNamespace(fastapi_app=dummy))
    monkeypatch.setitem(sys.modules, 'common.jwt_utils', types.SimpleNamespace(verify_token=lambda t: 'user'))

    req_mod = types.ModuleType('requests')
    def fake_request(method, url, params=None, headers=None, data=None, allow_redirects=False):
        capture['method'] = method
        capture['url'] = url
        capture['params'] = dict(params) if params else {}
        capture['headers'] = headers
        capture['data'] = data
        return types.SimpleNamespace(status_code=200, content=b'ok', headers={})
    req_mod.request = fake_request
    monkeypatch.setitem(sys.modules, 'requests', req_mod)

    if with_url:
        monkeypatch.setenv('GITEA_URL', 'http://gitea')
    else:
        monkeypatch.delenv('GITEA_URL', raising=False)

    spec = importlib.util.spec_from_file_location('chat_client.gateway_app', os.path.join(os.path.dirname(__file__), '..', 'chat_client', 'gateway_app.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules['chat_client.gateway_app'] = module
    spec.loader.exec_module(module)
    return module


def test_proxy_forwards_request(monkeypatch):
    capture = {}
    module = load_gateway_app(monkeypatch, capture)
    client = TestClient(module.app)
    resp = client.get('/store/foo?bar=1')
    assert resp.status_code == 200
    assert capture['url'] == 'http://gitea/foo'
    assert capture['params']['bar'] == '1'


def test_proxy_disabled(monkeypatch):
    capture = {}
    module = load_gateway_app(monkeypatch, capture, with_url=False)
    client = TestClient(module.app)
    resp = client.get('/store/foo')
    assert resp.status_code == 404

