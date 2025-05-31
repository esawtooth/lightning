import sys, os, types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agents import AGENT_REGISTRY


def test_echo_agent_registry():
    assert 'echo' in AGENT_REGISTRY
    agent = AGENT_REGISTRY['echo']
    result = agent.run(['hi', 'there'])
    assert result == 'hi\nthere'


def test_openai_shell_agent(monkeypatch):
    assert 'openai-shell' in AGENT_REGISTRY
    agent = AGENT_REGISTRY['openai-shell']

    captured = {}

    class ChatStub:
        @staticmethod
        def create(messages=None, model=None):
            captured['messages'] = messages
            captured['model'] = model
            return {"choices": [{"message": {"content": "echo hello"}}]}

    openai_stub = types.SimpleNamespace(ChatCompletion=ChatStub)
    monkeypatch.setitem(sys.modules, 'openai', openai_stub)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk')
    monkeypatch.setenv('OPENAI_MODEL', 'model-test')

    result = agent.run(['say hello'])
    assert 'hello' in result
    assert captured['model'] == 'model-test'
