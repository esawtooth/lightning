import os
import importlib
import types

from fastapi.testclient import TestClient


def load_app(monkeypatch, env=None):
    if env:
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
    import dashboard.app as app_module
    importlib.reload(app_module)
    return app_module


def test_tasks_page(monkeypatch):
    app_module = load_app(monkeypatch, {"API_BASE": "http://api", "AUTH_TOKEN": "tok"})
    client = TestClient(app_module.app)
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_tasks_json_success(monkeypatch):
    env = {"API_BASE": "http://api", "AUTH_TOKEN": "envtok"}
    app_module = load_app(monkeypatch, env)

    captured = {}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return types.SimpleNamespace(status_code=200, json=lambda: [{"id": "t1"}], text="")

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    client = TestClient(app_module.app)
    resp = client.get("/tasks.json")
    assert resp.status_code == 200
    assert resp.json() == [{"id": "t1"}]
    assert captured["url"] == "http://api/tasks"
    assert captured["headers"]["Authorization"] == "Bearer envtok"


def test_tasks_json_bad_token(monkeypatch):
    env = {"API_BASE": "http://api"}
    app_module = load_app(monkeypatch, env)

    def fake_get(url, headers=None):
        return types.SimpleNamespace(status_code=401, text="unauthorized", json=lambda: {})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    client = TestClient(app_module.app)
    resp = client.get("/tasks.json?token=bad")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "unauthorized"


def test_create_event_success(monkeypatch):
    env = {"API_BASE": "http://api"}
    app_module = load_app(monkeypatch, env)

    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return types.SimpleNamespace(status_code=200, text="", json=lambda: {})

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    client = TestClient(app_module.app)
    resp = client.post("/events?token=tok", json={"type": "test", "metadata": {"a": 1}})
    assert resp.status_code == 200
    assert resp.json() == {"status": "queued"}
    assert captured["url"] == "http://api/events"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["payload"]["type"] == "test"
    assert captured["payload"]["metadata"] == {"a": 1}


def test_create_event_missing_token(monkeypatch):
    env = {"API_BASE": "http://api", "AUTH_TOKEN": None}
    app_module = load_app(monkeypatch, env)

    client = TestClient(app_module.app)
    resp = client.post("/events", json={"type": "test", "metadata": {}})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing token"


def test_create_event_bad_token(monkeypatch):
    env = {"API_BASE": "http://api"}
    app_module = load_app(monkeypatch, env)

    def fake_post(url, json=None, headers=None):
        return types.SimpleNamespace(status_code=401, text="invalid", json=lambda: {})

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    client = TestClient(app_module.app)
    resp = client.post("/events?token=bad", json={"type": "t", "metadata": {}})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid"

