import json
import logging
from typing import Dict, Any

from jsonschema import validate, ValidationError

from .schema import PLAN_JSONSCHEMA, PlanModel

logger = logging.getLogger(__name__)

try:
    import pm4py
    from pm4py.objects.petri import utils as petri_utils

    HAVE_PETRI = True
except ImportError:  # pragma: no cover - optional dependency
    HAVE_PETRI = False
    logger.warning("pm4py not installed – structural checks disabled")


class PlanValidationError(Exception):
    pass


def _jsonschema_check(plan: Dict[str, Any]):
    try:
        validate(plan, PLAN_JSONSCHEMA)
    except ValidationError as e:
        raise PlanValidationError(f"JSON-Schema: {e.message}")


def _petri_net_check(plan: Dict[str, Any]):
    if not HAVE_PETRI:
        return
    import pm4py.objects.petri.petrinet as pn

    net = pn.PetriNet(plan["plan_name"])
    places = {ev: pn.PetriNet.Place(ev) for ev in plan["events"]}
    for p in places.values():
        net.places.add(p)
    trans = {}
    for name, step in plan["steps"].items():
        t = pn.PetriNet.Transition(name, name)
        trans[name] = t
        net.transitions.add(t)
        for e in step["on"]:
            net.add_arc(places[e], t)
        for e in step.get("emits", []):
            net.add_arc(t, places[e])
    if plan["graph_type"] == "acyclic":
        if petri_utils.check_wf_net_cycles(net):
            raise PlanValidationError("Cycle found in acyclic plan")
    # boundedness check placeholder


def validate_plan(plan: Dict[str, Any]):
    _jsonschema_check(plan)
    _petri_net_check(plan)
    PlanModel.model_validate(plan)
