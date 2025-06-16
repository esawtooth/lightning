import json
from pathlib import Path
from pydantic import BaseModel, Field, constr
from typing import Dict, List, Literal, Any

GRAPH_TYPE = Literal["acyclic", "reactive"]


class StepModel(BaseModel):
    on: List[str]
    action: str
    args: Dict[str, Any] = {}
    emits: List[str] | None = None
    guard: str | None = None


class PlanModel(BaseModel):
    plan_name: constr(min_length=1)
    graph_type: GRAPH_TYPE
    events: Dict[str, Dict[str, Any]]
    steps: Dict[str, StepModel]


PLAN_JSONSCHEMA = PlanModel.schema()


def dump_schema(path: str | Path):
    Path(path).write_text(json.dumps(PLAN_JSONSCHEMA, indent=2))
