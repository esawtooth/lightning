import os
import sys
import json
import types
import importlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def load_cosmos(monkeypatch, store):
    cosmos_mod = types.ModuleType('cosmos')

    class DummyContainer:
        def __init__(self):
            self.store = store
        def read_item(self, id, partition_key=None):
            key = (partition_key, id)
            if key not in self.store:
                raise Exception('nf')
            return self.store[key]
        def create_container_if_not_exists(self, *a, **k):
            return self

    class DummyDatabase:
        def create_container_if_not_exists(self, *a, **k):
            return DummyContainer()

    class DummyClient:
        def create_database_if_not_exists(self, *a, **k):
            return DummyDatabase()

    cosmos_mod.CosmosClient = types.SimpleNamespace(from_connection_string=lambda *a, **k: DummyClient())
    cosmos_mod.PartitionKey = lambda path: {'path': path}
    monkeypatch.setitem(sys.modules, 'azure.cosmos', cosmos_mod)


def test_policy_from_cosmos(monkeypatch):
    store = {('u1', 'policy'): {'id': 'policy', 'pk': 'u1', 'policy': {'prompt': 'hello', 'blocked_patterns': ['curl']}}}
    load_cosmos(monkeypatch, store)
    monkeypatch.setenv('COSMOS_CONNECTION', 'c')
    monkeypatch.setenv('COSMOS_DATABASE', 'd')
    monkeypatch.setenv('POLICY_CONTAINER', 'policies')
    monkeypatch.setenv('USER_ID', 'u1')
    import policy
    import importlib
    importlib.reload(policy)
    assert policy.get_policy_prompt() == 'hello'
    with pytest.raises(policy.PolicyViolationError):
        policy.validate_command('curl http://x')
