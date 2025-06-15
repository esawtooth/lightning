import os
import sys
import types
import subprocess
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "check_gh_actions",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "check-gh-actions.py"),
)
check_gh_actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_gh_actions)


def test_run_command_success(monkeypatch):
    called = {}

    def fake_run(cmd, shell=False, capture_output=False, text=False, check=False):
        called['cmd'] = cmd
        called['capture_output'] = capture_output
        return types.SimpleNamespace(stdout='out\n')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    out = check_gh_actions.run_command('echo 1')
    assert out == 'out'
    assert called['cmd'] == 'echo 1'
    assert called['capture_output']


def test_run_command_error(monkeypatch, capsys):
    def fake_run(*a, **k):
        raise subprocess.CalledProcessError(1, 'cmd', stderr='bad')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        check_gh_actions.run_command('boom')
    out = capsys.readouterr().out
    assert 'Error running command' in out


def test_format_datetime():
    iso = '2023-01-02T03:04:05Z'
    assert check_gh_actions.format_datetime(iso) == '2023-01-02 03:04:05 UTC'
    assert check_gh_actions.format_datetime('bad') == 'bad'
