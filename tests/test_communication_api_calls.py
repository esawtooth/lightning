import asyncio
import types
import sys
import os
import smtplib

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vextir_os.communication_drivers import EmailConnectorDriver, CalendarConnectorDriver


def setup_driver_env(monkeypatch):
    monkeypatch.setenv("GMAIL_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("OUTLOOK_OAUTH_TOKEN", "otok")
    monkeypatch.setenv("ICLOUD_USERNAME", "user@icloud.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "pass")


def test_send_via_gmail(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    def fake_post(url, headers=None, json=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr('requests.post', fake_post)

    driver = EmailConnectorDriver(EmailConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._send_via_gmail('u', {'to': 'a@example.com', 'subject': 's', 'body': 'b'}))
    assert res is True
    assert captured['url'].startswith('https://gmail')
    assert 'Bearer tok' in captured['headers']['Authorization']

def test_send_via_outlook(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    def fake_post(url, headers=None, json=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr('requests.post', fake_post)

    driver = EmailConnectorDriver(EmailConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._send_via_outlook('u', {'to': 'a@example.com', 'subject': 's', 'body': 'b'}))
    assert res is True
    assert captured['url'].startswith('https://graph.microsoft.com')
    assert 'Bearer otok' in captured['headers']['Authorization']

def test_send_via_icloud(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    class DummySMTP:
        def __init__(self, host, port):
            captured['host'] = host
            captured['port'] = port
        def login(self, user, pwd):
            captured['login'] = (user, pwd)
        def sendmail(self, from_addr, to_addrs, msg):
            captured['msg'] = msg
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(smtplib, 'SMTP_SSL', DummySMTP)

    driver = EmailConnectorDriver(EmailConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._send_via_icloud('u', {'to': 'a@example.com', 'subject': 's', 'body': 'b'}))
    assert res is True
    assert captured['login'] == ('user@icloud.com', 'pass')

def test_create_via_google_calendar(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    def fake_post(url, headers=None, json=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return types.SimpleNamespace(status_code=201)

    monkeypatch.setattr('requests.post', fake_post)

    driver = CalendarConnectorDriver(CalendarConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._create_via_google_calendar('u', {'title': 't', 'start_time': 's', 'end_time': 'e'}))
    assert res is True
    assert captured['url'].startswith('https://www.googleapis.com/calendar')
    assert 'Bearer tok' in captured['headers']['Authorization']

def test_create_via_outlook_calendar(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    def fake_post(url, headers=None, json=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return types.SimpleNamespace(status_code=201)

    monkeypatch.setattr('requests.post', fake_post)

    driver = CalendarConnectorDriver(CalendarConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._create_via_outlook_calendar('u', {'title': 't', 'start_time': 's', 'end_time': 'e'}))
    assert res is True
    assert captured['url'].startswith('https://graph.microsoft.com')
    assert 'Bearer otok' in captured['headers']['Authorization']

def test_create_via_icloud_calendar(monkeypatch):
    setup_driver_env(monkeypatch)
    captured = {}

    def fake_post(url, data=None, headers=None, auth=None):
        captured['url'] = url
        captured['data'] = data
        captured['headers'] = headers
        captured['auth'] = auth
        return types.SimpleNamespace(status_code=201)

    monkeypatch.setattr('requests.post', fake_post)

    driver = CalendarConnectorDriver(CalendarConnectorDriver._vextir_manifest)
    res = asyncio.run(driver._create_via_icloud_calendar('u', {'title': 't', 'start_time': 's', 'end_time': 'e'}))
    assert res is True
    assert captured['auth'] == ('user@icloud.com', 'pass')

