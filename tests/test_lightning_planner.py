import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import lightning_planner as lp

SAMPLE_PLAN = {
    "plan_name": "sample",
    "graph_type": "acyclic",
    "events": {"start": {}, "done": {}},
    "steps": {
        "first": {
            "on": ["start"],
            "action": "send_email",
            "args": {"to": "a", "subject": "b", "body": "c"},
            "emits": ["done"],
        }
    },
}


def test_registry_subset():
    subset = lp.ToolRegistry.subset("email")
    assert "send_email" in subset
    assert "read_email" in subset


def test_validate_plan():
    lp.validate_plan(SAMPLE_PLAN)


def test_call_planner_llm():
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(function_call=SimpleNamespace(name="create_plan", arguments=json.dumps(SAMPLE_PLAN))))]
    with patch("lightning_planner.planner.openai_client.chat.completions.create", return_value=fake_resp):
        plan = lp.call_planner_llm("do it", lp.ToolRegistry.load())
    assert plan == SAMPLE_PLAN


def test_create_verified_plan():
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(function_call=SimpleNamespace(name="create_plan", arguments=json.dumps(SAMPLE_PLAN))))]
    with patch("lightning_planner.planner.openai_client.chat.completions.create", return_value=fake_resp), \
         patch("lightning_planner.storage.COSMOS", False):
        bundle = lp.create_verified_plan("instr", user_id="u")
    assert bundle["plan"] == SAMPLE_PLAN
    assert "plan_id" in bundle
