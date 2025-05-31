import json
import os
import sys
import types
from datetime import datetime

import pytest


def create_stub_modules(monkeypatch):
    azure_mod = types.ModuleType("azure")
    func_mod = types.ModuleType("azure.functions")
    func_mod.ServiceBusMessage = object
    servicebus_mod = types.ModuleType("azure.servicebus")

    class DummyClient:
        @classmethod
        def from_connection_string(cls, *_):
            return DummyClient()

    servicebus_mod.ServiceBusClient = DummyClient
    servicebus_mod.ServiceBusMessage = object

    azure_mod.functions = func_mod
    azure_mod.servicebus = servicebus_mod

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.functions", func_mod)
    monkeypatch.setitem(sys.modules, "azure.servicebus", servicebus_mod)

    openai_mod = types.ModuleType("openai")

    class DummyChat:
        @staticmethod
        def create(*args, **kwargs):
            raise AssertionError("OpenAI should not be called")

    openai_mod.ChatCompletion = DummyChat
    monkeypatch.setitem(sys.modules, "openai", openai_mod)


def test_unrelated_event_skipped(monkeypatch):
    create_stub_modules(monkeypatch)
    monkeypatch.setenv("SERVICEBUS_CONNECTION", "conn")
    monkeypatch.setenv("SERVICEBUS_QUEUE", "queue")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "chatresponder", "azure-function/ChatResponder/__init__.py"
    )
    chat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat)

    class StubMessage:
        def __init__(self, body):
            self._body = body

        def get_body(self):
            return self._body

    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "t",
        "type": "other.event",
        "userID": "u1",
        "metadata": {"messages": [{"role": "user", "content": "hi"}]},
    }
    msg = StubMessage(json.dumps(event).encode())

    # Should not raise AssertionError from DummyChat.create
    chat.main(msg)
