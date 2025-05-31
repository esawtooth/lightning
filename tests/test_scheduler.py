import os
import sys
import json
import types
import importlib.util
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_scheduler(monkeypatch, capture):
    azure_mod = types.ModuleType('azure')
    tables_mod = types.ModuleType('tables')
    class DummyTable:
        def create_table_if_not_exists(self):
            pass
        def upsert_entity(self, entity):
            capture['entity'] = entity
    class DummyService:
        def get_table_client(self, table):
            return DummyTable()
    tables_mod.TableServiceClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyService()
    )
    azure_mod.data = types.SimpleNamespace(tables=tables_mod)
    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.data.tables', tables_mod)

    func_mod = types.ModuleType('functions')
    class DummyResponse:
        def __init__(self, body='', status_code=200, mimetype=None):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype
    class DummyRequest:
        pass
    func_mod.HttpResponse = DummyResponse
    func_mod.HttpRequest = DummyRequest
    azure_mod.functions = func_mod
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)

    cron_mod = types.ModuleType('croniter')
    cron_mod.croniter = lambda expr, start: types.SimpleNamespace(get_next=lambda typ: start + timedelta(minutes=5))
    monkeypatch.setitem(sys.modules, 'croniter', cron_mod)

    spec = importlib.util.spec_from_file_location(
        'Scheduler', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'Scheduler', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['Scheduler'] = module
    spec.loader.exec_module(module)
    return module


def test_schedule_creation(monkeypatch):
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['SCHEDULE_TABLE'] = 't'
    capture = {}
    mod = load_scheduler(monkeypatch, capture)

    event = {
        'timestamp': datetime.utcnow().isoformat(),
        'source': 's',
        'type': 't',
        'metadata': {}
    }
    req = types.SimpleNamespace(
        get_json=lambda: {'event': event, 'timestamp': (datetime.utcnow() + timedelta(hours=1)).isoformat()},
        headers={'x-user-id': 'u1'}
    )
    resp = mod.main(req)
    assert resp.status_code == 201
    assert capture['entity']['PartitionKey'] == 'u1'


def load_worker(monkeypatch, schedules, sent):
    azure_mod = types.ModuleType('azure')
    tables_mod = types.ModuleType('tables')
    class DummyTable:
        def query_entities(self, *a, **k):
            return schedules
        def update_entity(self, e):
            sent['updated'] = e
        def delete_entity(self, pk, rk):
            sent.setdefault('deleted', []).append((pk, rk))
    class DummyService:
        def get_table_client(self, table):
            return DummyTable()
    tables_mod.TableServiceClient = types.SimpleNamespace(
        from_connection_string=lambda *a, **k: DummyService()
    )
    azure_mod.data = types.SimpleNamespace(tables=tables_mod)
    monkeypatch.setitem(sys.modules, 'azure', azure_mod)
    monkeypatch.setitem(sys.modules, 'azure.data.tables', tables_mod)

    sb_mod = types.ModuleType('servicebus')
    class DummySender:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def send_messages(self, msg):
            sent.setdefault('messages', []).append(json.loads(msg.body))
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
    class DummyMessage:
        def __init__(self, body):
            self.body = body
            self.application_properties = {}
    sb_mod.ServiceBusMessage = DummyMessage
    azure_mod.servicebus = sb_mod
    monkeypatch.setitem(sys.modules, 'azure.servicebus', sb_mod)

    func_mod = types.ModuleType('functions')
    azure_mod.functions = func_mod
    class DummyTimer:
        pass
    func_mod.TimerRequest = DummyTimer
    monkeypatch.setitem(sys.modules, 'azure.functions', func_mod)

    cron_mod = types.ModuleType('croniter')
    cron_mod.croniter = lambda expr, start: types.SimpleNamespace(get_next=lambda typ: start + timedelta(minutes=5))
    monkeypatch.setitem(sys.modules, 'croniter', cron_mod)

    spec = importlib.util.spec_from_file_location(
        'ScheduleWorker', os.path.join(os.path.dirname(__file__), '..', 'azure-function', 'ScheduleWorker', '__init__.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['ScheduleWorker'] = module
    spec.loader.exec_module(module)
    return module


def test_worker_publishes_event(monkeypatch):
    os.environ['STORAGE_CONNECTION'] = 'c'
    os.environ['SCHEDULE_TABLE'] = 't'
    os.environ['SERVICEBUS_CONNECTION'] = 'sb'
    os.environ['SERVICEBUS_QUEUE'] = 'q'

    event = {'timestamp': datetime.utcnow().isoformat(), 'source': 's', 'type': 't', 'userID': 'u1', 'metadata': {}}
    schedules = [{
        'PartitionKey': 'u1',
        'RowKey': '1',
        'event': json.dumps(event),
        'runAt': (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
        'cron': ''
    }]
    sent = {}
    mod = load_worker(monkeypatch, schedules, sent)
    mod.main(None)
    assert sent['messages'][0]['type'] == 't'
    assert ('u1', '1') in sent['deleted']
