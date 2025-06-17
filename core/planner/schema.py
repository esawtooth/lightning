import json
from pathlib import Path
from pydantic import BaseModel, Field, constr
from typing import Dict, List, Literal, Any

# schema.py
from pydantic import BaseModel, Field, constr, ConfigDict
from typing import Literal, List, Dict, Optional, Union

GRAPH_TYPE = Literal["acyclic", "reactive"]

from pydantic import BaseModel, Field, constr, ConfigDict
from typing import List, Literal, Dict, Optional

EXTERNAL_EVENT_TYPES = Literal["time.cron", "time.interval", "webhook", "manual"]

class ExternalEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1, pattern=r"^event\.")
    kind: EXTERNAL_EVENT_TYPES          # new, required
    schedule: Optional[str] = None      # cron string or ISO‑8601 duration
    description: Optional[str] = None

class ToolRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: constr(min_length=1)        # must exist in ToolRegistry
    args: Dict[str, str] = Field(default_factory=dict)

class StepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1)
    on: List[str]
    action: constr(min_length=1)
    args: Dict[str, str] = Field(default_factory=dict)
    emits: List[str] = Field(default_factory=list)
    guard: Optional[str] = None

class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_name: constr(min_length=1)
    graph_type: Literal["acyclic", "reactive"]
    events: List[ExternalEventModel]        # now *typed* external events
    steps: List[StepModel]


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: constr(min_length=1)
    description: Optional[str] = None
    # add other metadata if you need

class EmailArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: str
    since: str            # ISO‑8601

class SummarizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    style: str

ArgsUnion = EmailArgs | SummarizeArgs | None


PLAN_JSONSCHEMA = PlanModel.schema()


def dump_schema(path: str | Path):
    Path(path).write_text(json.dumps(PLAN_JSONSCHEMA, indent=2))
