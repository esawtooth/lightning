import os
import sys
import json
import types
import importlib.util
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_chat_responder(monkeypatch, capture):
    # stub openai module
    openai_stub = types.ModuleType("openai")

    class ChatStub:
        @staticmethod
        def create(messages=None, model=None):
            capture["model"] = model
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 7},
            }

    openai_stub.ChatCompletion = ChatStub
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    # stub azure functions
    azure_mod = types.ModuleType("azure")
    func_mod = types.ModuleType("functions")

    class DummySBMessage:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def get_body(self):
            return self._body

    func_mod.ServiceBusMessage = DummySBMessage
    azure_mod.functions = func_mod

    sb_mod = types.ModuleType("servicebus")

    class DummySender:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def send_messages(self, msg):
            capture["out"] = json.loads(msg.body)

    class DummyClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def get_queue_sender(self, queue_name=None):
            return DummySender()

    sb_mod.ServiceBusClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyClient()
    )

    class DummyOutMessage:
        def __init__(self, body):
            self.body = body
            self.application_properties = {}

    sb_mod.ServiceBusMessage = DummyOutMessage
    azure_mod.servicebus = sb_mod

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.functions", func_mod)
    monkeypatch.setitem(sys.modules, "azure.servicebus", sb_mod)

    spec = importlib.util.spec_from_file_location(
        "ChatResponder",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "azure-function",
            "ChatResponder",
            "__init__.py",
        ),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ChatResponder"] = module
    spec.loader.exec_module(module)
    return module, func_mod.ServiceBusMessage


def test_openai_model_env(monkeypatch):
    os.environ["SERVICEBUS_CONNECTION"] = "endpoint"
    os.environ["SERVICEBUS_QUEUE"] = "queue"
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["OPENAI_API_KEY"] = "sk-test"

    captured = {}
    module, SBMessage = load_chat_responder(monkeypatch, captured)

    event = {
        "timestamp": "2023-01-01T00:00:00Z",
        "source": "test",
        "type": "llm.chat",
        "userID": "u",
        "metadata": {"messages": [{"role": "user", "content": "hi"}]},
    }
    msg = SBMessage(json.dumps(event))
    module.main(msg)

    assert captured["model"] == "test-model"
    assert captured["out"]["metadata"]["usage"]["total_tokens"] == 7


def test_missing_api_key(monkeypatch):
    os.environ["SERVICEBUS_CONNECTION"] = "endpoint"
    os.environ["SERVICEBUS_QUEUE"] = "queue"
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]

    with pytest.raises(RuntimeError):
        load_chat_responder(monkeypatch, {})
