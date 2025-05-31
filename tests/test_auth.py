import os
import sys
import time
import importlib.util
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt


def load_auth():
    path = os.path.join(os.path.dirname(__file__), "..", "azure-function", "auth.py")
    spec = importlib.util.spec_from_file_location("auth", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['auth'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_expired_token(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    token = jwt.encode({'sub': 'u', 'exp': time.time() - 10}, 'k')
    auth = load_auth()
    with pytest.raises(ValueError):
        auth.verify_token('Bearer ' + token)


def test_invalid_issuer(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ['ISSUER'] = 'good'
    token = jwt.encode({'sub': 'u', 'exp': time.time() + 60, 'iss': 'bad'}, 'k')
    auth = load_auth()
    with pytest.raises(ValueError):
        auth.verify_token('Bearer ' + token)
