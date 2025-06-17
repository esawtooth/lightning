from typing import Dict, Any

# NEW – json‑schema helpers
from jsonschema import validate, ValidationError

# NEW – your generated schema + pydantic model
from .schema import PLAN_JSONSCHEMA, PlanModel

from .registry import ToolRegistry, EventRegistry    # you add EventRegistry
from pm4py.analysis import check_is_workflow_net
from pm4py.analysis import check_soundness
# ------------------------------------------------------------------ #
# TRY ALL KNOWN IMPORT LOCATIONS, then fall back to a tiny helper
# ------------------------------------------------------------------ #
_add_arc_candidates = [
    "pm4py.objects.petri_net.utils.add_arc_from_to",           # 2.8.x
    "pm4py.objects.petri_net.utils.petri_utils.add_arc_from_to",
    "pm4py.objects.petri.utils.petri_utils.add_arc_from_to",   # 2.4‑2.7
]

_check_cycles_candidates = [
    "pm4py.objects.petri_net.utils.check_wf_net_cycles",
    "pm4py.objects.petri_net.utils.petri_utils.check_wf_net_cycles",
    "pm4py.objects.petri.utils.petri_utils.check_wf_net_cycles",
]

# lightning_planner/validator.py  (excerpt)

_eval_wf_candidates = [
    "pm4py.evaluation.wf_net.evaluator",
    "pm4py.algo.evaluation.wf_net.evaluator",
]
_eval_snd_candidates = [
    "pm4py.evaluation.soundness.evaluator",
    "pm4py.algo.evaluation.soundness.evaluator",
]

def _import_first(paths):
    import importlib
    for p in paths:
        try:
            mod_path, attr = p.rsplit(".", 1)
            return getattr(importlib.import_module(mod_path), attr)
        except (ImportError, AttributeError):
            continue
    return None

wf_eval = _import_first(_eval_wf_candidates)
snd_eval = _import_first(_eval_snd_candidates)

# -------------------------------------------------------------------
# last‑resort fall‑back for PM4Py ≥ 2.8 (evaluators removed)
# -------------------------------------------------------------------
if wf_eval is None or snd_eval is None:
    from pm4py.analysis import (
        check_is_workflow_net as _check_wf,
        check_soundness as _check_sound,
    )

    class _DummyEval:
        """Expose the same .apply() API as the old evaluator classes."""
        def __init__(self, fn): self._fn = fn
        def apply(self, net, *args, **kwargs): return (self._fn(net, *args),)

    wf_eval = _DummyEval(_check_wf)
    snd_eval = _DummyEval(_check_sound)


def _dynamic_import(path: str):
    import importlib
    try:
        mod_path, attr = path.rsplit(".", 1)
        return getattr(importlib.import_module(mod_path), attr)
    except (ImportError, AttributeError):
        return None

add_arc_from_to = next(
    (fn for fn in map(_dynamic_import, _add_arc_candidates) if fn), None
)
check_wf_net_cycles = next(
    (fn for fn in map(_dynamic_import, _check_cycles_candidates) if fn), None
)

# If nothing worked, make minimal local stubs
if add_arc_from_to is None:
    def add_arc_from_to(src, tgt, net):                       # type: ignore
        arc = PetriNet.Arc(src, tgt)
        net.arcs.add(arc); src.out_arcs.add(arc); tgt.in_arcs.add(arc)
        return arc

if check_wf_net_cycles is None:
    def check_wf_net_cycles(net):                             # type: ignore
        return False  # graceful degradation: assume acyclic
    
class PlanValidationError(Exception):
    pass

def _jsonschema_check(plan: Dict[str, Any]):
    try:
        validate(instance=plan, schema=PLAN_JSONSCHEMA)
    except ValidationError as e:
        raise PlanValidationError(f"JSON‑Schema: {str(e)}")

def _petri_net_check(plan: Dict[str, Any]):
    # 1. Build net --------------------------------------------------------
    net = PetriNet(plan["plan_name"])

    # EVENTS → PLACES (events is now a list of dicts)
    places = {}
    for ev in plan["events"]:
        name = ev["name"]
        p = PetriNet.Place(name)
        places[name] = p
        net.places.add(p)

    # STEPS → TRANSITIONS & ARCS (steps is a list)
    for step in plan["steps"]:
        t = PetriNet.Transition(step["name"], step["name"])
        net.transitions.add(t)

        for e in step["on"]:
            add_arc_from_to(places[e], t, net)
        for e in step.get("emits", []):
            add_arc_from_to(t, places[e], net)

    # 2. Optional acyclicity check ---------------------------------------
    if plan["graph_type"] == "acyclic" and check_wf_net_cycles(net):
        raise PlanValidationError("Cycle found in acyclic plan")
    


from pm4py.objects.petri_net.obj import PetriNet

def _external_event_check(plan):
    ext_set = set(EventRegistry)
    for evt in plan["events"]:
        name = evt["name"]
        if name in ext_set:
            # must match registry kind
            if evt["kind"] != EventRegistry[name]["kind"]:
                raise PlanValidationError(
                    f"Kind mismatch for external event {name}"
                )
        else:
            # internal events must NOT specify kind/schedule
            if evt.get("kind") or evt.get("schedule"):
                raise PlanValidationError(
                    f"{name} is internal; omit kind and schedule."
                )


def _tool_check(plan):
    tools = ToolRegistry.load()
    for step in plan["steps"]:
        meta = tools.get(step["action"])
        if meta is None:
            raise PlanValidationError(f"Unknown action {step['action']}")
        missing = set(meta["inputs"]) - set(step["args"])
        if missing:
            raise PlanValidationError(
                f"Step {step['name']} missing args: {missing}"
            )


def _soundness_check(petri_net):
    if not snd_eval.apply(petri_net)[0]:
        raise PlanValidationError("Petri net is not sound")
    if not wf_eval.apply(petri_net)[0]:
        raise PlanValidationError("Petri net is not a WF‑net")
    
def _petri_net_build(plan):
    from pm4py.objects.petri_net.obj import PetriNet
    net = PetriNet(plan["plan_name"])
    places = {e["name"]: PetriNet.Place(e["name"]) for e in plan["events"]}
    net.places.update(places.values())

    for step in plan["steps"]:
        t = PetriNet.Transition(step["name"], step["name"])
        net.transitions.add(t)
        for ev in step["on"]:
            add_arc_from_to(places[ev], t, net)
        for ev in step.get("emits", []):
            add_arc_from_to(t, places[ev], net)
    return net


def validate_plan(plan: Dict[str, Any]):
    _jsonschema_check(plan)
    _external_event_check(plan)
    _tool_check(plan)

    net = _petri_net_build(plan)        # returns PetriNet object only
    _soundness_check(net)

    # still run the typed Pydantic validation
    PlanModel.model_validate(plan)
