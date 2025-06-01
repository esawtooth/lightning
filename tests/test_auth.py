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
    os.environ['ISSUER'] = 'good'
    token = jwt.encode({'sub': 'u', 'exp': time.time() + 60, 'iss': 'bad'}, 'k')
    with pytest.raises(ValueError):
        verify_token('Bearer ' + token)
