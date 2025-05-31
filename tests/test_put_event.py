import os
import sys
import json
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_put_event(monkeypatch, capture):
    azure_mod = types.ModuleType('azure')
    func_mod = types.ModuleType('functions')

    class DummyHttpRequest:
        def __init__(self, body=None, headers=None):
            self._body = body
            self.headers = headers or {}

        def get_json(self):
            if self._body is None:
                raise ValueError("no body")
            return json.loads(self._body)

    class DummyHttpResponse:
        def __init__(self, body, status_code=200):
            self.body = body
            self.status_code = status_code

    func_mod.HttpRequest = DummyHttpRequest
    func_mod.HttpResponse = DummyHttpResponse
    azure_mod.functions = func_mod

    sb_mod = types.ModuleType('servicebus')

    class DummySender:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def send_messages(self, msg):
            capture['message'] = msg

    class DummyClient:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def get_queue_sender(self, queue_name=None):
            capture['queue'] = queue_name
            return DummySender()

    sb_mod.ServiceBusClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyClient()
    )

    class DummyMessage:
        def __init__(self, body):
            self.body = body
            self.application_properties = {}

    sb_mod.ServiceBusMessage = DummyMessage
    azure_mod.servicebus = sb_mod

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)
    monkeypatch.setitem(sys.modules, 'azure.servicebus', sb_mod)

    spec = importlib.util.spec_from_file_location(
        'PutEvent',
        os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'PutEvent', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['PutEvent'] = module
    spec.loader.exec_module(module)
    return module, DummyHttpRequest


def test_invalid_json(monkeypatch):
    os.environ['SERVICEBUS_CONNECTION'] = 'endpoint'
    os.environ['SERVICEBUS_QUEUE'] = 'q'
    captured = {}
    module, HttpRequest = load_put_event(monkeypatch, captured)

    req = HttpRequest(body='not-json', headers={'x-user-id': 'u'})
    resp = module.main(req)
    assert resp.status_code == 400
    assert 'message' not in captured


def test_missing_user_id(monkeypatch):
    os.environ['SERVICEBUS_CONNECTION'] = 'endpoint'
    os.environ['SERVICEBUS_QUEUE'] = 'q'
    captured = {}
    module, HttpRequest = load_put_event(monkeypatch, captured)

    event = {
        'timestamp': '2023-01-01T00:00:00Z',
        'source': 'test',
        'type': 't'
    }
    req = HttpRequest(body=json.dumps(event))
    resp = module.main(req)
    assert resp.status_code == 400
    assert 'message' not in captured


def test_valid_request(monkeypatch):
    os.environ['SERVICEBUS_CONNECTION'] = 'endpoint'
    os.environ['SERVICEBUS_QUEUE'] = 'q'
    captured = {}
    module, HttpRequest = load_put_event(monkeypatch, captured)

    event = {
        'timestamp': '2023-01-01T00:00:00Z',
        'source': 'test',
        'type': 'sample',
        'metadata': {'a': 1}
    }
    req = HttpRequest(body=json.dumps(event), headers={'x-user-id': 'u'})
    resp = module.main(req)
    assert resp.status_code == 202
    assert 'message' in captured
    body = json.loads(captured['message'].body)
    assert body['userID'] == 'u'
