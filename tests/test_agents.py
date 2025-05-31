import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agents import AGENT_REGISTRY


def test_echo_agent_registry():
    assert 'echo' in AGENT_REGISTRY
    agent = AGENT_REGISTRY['echo']
    result = agent.run(['hi', 'there'])
    assert result == 'hi\nthere'
