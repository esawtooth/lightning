import sys, os, types, subprocess, pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agents import AGENT_REGISTRY


def test_echo_agent_registry():
    assert "echo" in AGENT_REGISTRY
    agent = AGENT_REGISTRY["echo"]
    result = agent.run(["hi", "there"])
    assert result == "hi\nthere"


def test_openai_shell_agent(monkeypatch, capsys):
    assert "openai-shell" in AGENT_REGISTRY
    agent = AGENT_REGISTRY["openai-shell"]

    captured = {}

    class ChatStub:
        @staticmethod
        def create(messages=None, model=None, tools=None, tool_choice=None):
            captured["messages"] = messages
            captured["model"] = model
            captured["tools"] = tools
            captured["tool_choice"] = tool_choice
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"function": {"arguments": '{"command": "echo hello"}'}}
                            ]
                        }
                    }
                ],
                "usage": {"total_tokens": 5},
            }

    openai_stub = types.SimpleNamespace(ChatCompletion=ChatStub)
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    def stub_run(cmd, shell=False, capture_output=False, text=False):
        captured["cmd"] = cmd
        return types.SimpleNamespace(stdout="hello\n", stderr="")

    monkeypatch.setattr(subprocess, "run", stub_run)
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_MODEL", "model-test")

    result = agent.run("say hello")
    out = capsys.readouterr().out
    assert "$ echo hello" in out
    assert "hello" in out
    assert "hello" in result
    assert captured["model"] == "model-test"
    assert captured["tools"][0]["function"]["name"] == "bash"
    assert agent.last_usage["total_tokens"] == 5


def test_openai_shell_missing_api_key(monkeypatch):
    agent = AGENT_REGISTRY["openai-shell"]
    openai_stub = types.SimpleNamespace(
        ChatCompletion=types.SimpleNamespace(create=lambda **k: {"choices": []})
    )
    monkeypatch.setitem(sys.modules, "openai", openai_stub)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        agent.run("cmd")


def test_openai_shell_missing_library(monkeypatch):
    agent = AGENT_REGISTRY["openai-shell"]
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    import builtins as _builtins

    orig_import = _builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "openai":
            raise ModuleNotFoundError
        return orig_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(_builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError):
        agent.run("cmd")
