import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, constr

# Import unified event system
from ..events import ExternalEventType, PlannerEventModel

GRAPH_TYPE = Literal["acyclic", "reactive"]

# Use the unified event model
ExternalEventModel = PlannerEventModel


class ToolRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: constr(min_length=1)  # must exist in ToolRegistry
    args: Dict[str, str] = Field(default_factory=dict)


class StepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1)
    on: List[str]
    action: constr(min_length=1)
    args: Dict[str, str] = Field(default_factory=dict)
    emits: List[str] = Field(default_factory=list)
    guard: Optional[str] = None
    description: Optional[str] = None


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_name: constr(min_length=1)
    graph_type: Literal["acyclic", "reactive"]
    events: List[ExternalEventModel]  # now *typed* external events
    steps: List[StepModel]
    description: Optional[str] = None


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1)
    description: Optional[str] = None
    # add other metadata if you need


class EmailArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: str
    since: str  # ISO‑8601


class SummarizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    style: str


ArgsUnion = EmailArgs | SummarizeArgs | None


PLAN_JSONSCHEMA = PlanModel.model_json_schema()


def dump_schema(path: str | Path):
    Path(path).write_text(json.dumps(PLAN_JSONSCHEMA, indent=2))
