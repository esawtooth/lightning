import sys, os, types, subprocess, pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agents import AGENT_REGISTRY


def test_conseil_agent(monkeypatch):
    assert "conseil" in AGENT_REGISTRY
    agent = AGENT_REGISTRY["conseil"]

    captured = {}

    def stub_run(cmd, capture_output=False, text=False):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(subprocess, "run", stub_run)

    result = agent.run("do something")
    assert "conseil" in captured["cmd"][0]
    assert "do something" in captured["cmd"][1]
    assert "done" in result
