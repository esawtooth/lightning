import os
import sys
import json
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_user_messenger(monkeypatch, capture):
    requests_mod = types.ModuleType('requests')

    def dummy_post(url, json=None):
        capture['url'] = url
        capture['json'] = json
    requests_mod.post = dummy_post

    monkeypatch.setitem(sys.modules, 'requests', requests_mod)

    azure_mod = types.ModuleType('azure')
    func_mod = types.ModuleType('functions')

    class DummyMessage:
        def __init__(self, body):
            self._body = body.encode('utf-8')
        def get_body(self):
            return self._body

    func_mod.ServiceBusMessage = DummyMessage
    azure_mod.functions = func_mod

    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)

    spec = importlib.util.spec_from_file_location(
        'UserMessenger',
        os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'UserMessenger', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['UserMessenger'] = module
    spec.loader.exec_module(module)
    return module, DummyMessage


def test_non_matching_event(monkeypatch):
    os.environ['NOTIFY_URL'] = 'http://notify'
    captured = {}
    module, SBMessage = load_user_messenger(monkeypatch, captured)

    event = {
        'timestamp': '2023-01-01T00:00:00Z',
        'source': 'test',
        'type': 'other.event',
        'userID': 'u',
        'metadata': {'message': 'hi'}
    }
    msg = SBMessage(json.dumps(event))
    module.main(msg)
    assert 'url' not in captured


def test_user_message_event(monkeypatch):
    os.environ['NOTIFY_URL'] = 'http://notify'
    captured = {}
    module, SBMessage = load_user_messenger(monkeypatch, captured)

    event = {
        'timestamp': '2023-01-01T00:00:00Z',
        'source': 'test',
        'type': 'user.message',
        'userID': 'u',
        'metadata': {'message': 'hi'}
    }
    msg = SBMessage(json.dumps(event))
    module.main(msg)
    assert captured['url'] == 'http://notify'
    assert captured['json'] == {'user_id': 'u', 'message': 'hi'}


def test_chat_response_event(monkeypatch):
    os.environ['NOTIFY_URL'] = 'http://notify'
    captured = {}
    module, SBMessage = load_user_messenger(monkeypatch, captured)

    event = {
        'timestamp': '2023-01-01T00:00:00Z',
        'source': 'ChatResponder',
        'type': 'llm.chat.response',
        'userID': 'u',
        'metadata': {'reply': 'ok'}
    }
    msg = SBMessage(json.dumps(event))
    module.main(msg)
    assert captured['url'] == 'http://notify'
    assert captured['json'] == {'user_id': 'u', 'message': 'ok'}
