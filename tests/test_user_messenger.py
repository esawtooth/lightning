import os
import sys
import types
import asyncio
from datetime import datetime
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from events import Event
from vextir_os.communication_drivers import UserMessengerDriver


def load_user_messenger_driver(monkeypatch, capture):
    servicebus_mod = types.ModuleType("servicebus")
    servicebus_mod.ServiceBusClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "azure.servicebus", servicebus_mod)

    driver = UserMessengerDriver(UserMessengerDriver._vextir_manifest)

    async def dummy_send(user_id, recipient, message, channel):
        capture["message"] = {
            "user_id": user_id,
            "recipient": recipient,
            "message": message,
            "channel": channel,
        }
        return True

    async def dummy_deliver(user_id, data):
        capture["notification"] = data
        return True

    monkeypatch.setattr(driver, "_send_message", dummy_send)
    monkeypatch.setattr(driver, "_deliver_notification", dummy_deliver)

    return driver


def test_non_matching_event(monkeypatch):
    capture = {}
    driver = load_user_messenger_driver(monkeypatch, capture)

    event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="other.event",
        user_id="u",
        metadata={"message": "hi"},
    )

    results = asyncio.run(driver.handle_event(event))
    assert results == []
    assert capture == {}


def test_user_message_event(monkeypatch):
    capture = {}
    driver = load_user_messenger_driver(monkeypatch, capture)

    event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="message.send",
        user_id="u",
        metadata={"recipient": "r", "message": "hi", "channel": "email"},
    )

    results = asyncio.run(driver.handle_event(event))
    assert results[0].type == "message.sent"
    assert capture["message"]["recipient"] == "r"


def test_notification_event(monkeypatch):
    capture = {}
    driver = load_user_messenger_driver(monkeypatch, capture)

    event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="notification.deliver",
        user_id="u",
        metadata={"title": "hi", "message": "ok", "channels": ["email"]},
    )

    results = asyncio.run(driver.handle_event(event))
    assert results[0].type == "notification.delivered"
    assert capture["notification"]["title"] == "hi"
