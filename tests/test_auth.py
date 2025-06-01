import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt
from common.jwt_utils import verify_token


def test_expired_token(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    token = jwt.encode({'sub': 'u', 'exp': time.time() - 10}, 'k')
    with pytest.raises(ValueError):
        verify_token('Bearer ' + token)


def test_invalid_issuer(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    monkeypatch.setenv('ISSUER', 'good')
    token = jwt.encode({'sub': 'u', 'exp': time.time() + 60, 'iss': 'bad'}, 'k')
    with pytest.raises(ValueError):
        verify_token('Bearer ' + token)


def test_valid_token(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    os.environ.pop('ISSUER', None)
    token = jwt.encode({'sub': 'u1', 'exp': time.time() + 60}, 'k')
    assert verify_token('Bearer ' + token) == 'u1'


def test_missing_signing_key(monkeypatch):
    os.environ.pop('JWT_SIGNING_KEY', None)
    with pytest.raises(RuntimeError):
        verify_token('tok')


def test_missing_user_id(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    token = jwt.encode({'exp': time.time() + 60}, 'k')
    with pytest.raises(ValueError):
        verify_token(token)



def test_missing_token(monkeypatch):
    os.environ['JWT_SIGNING_KEY'] = 'k'
    with pytest.raises(ValueError):
        verify_token('')
