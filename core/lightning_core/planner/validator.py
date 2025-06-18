"""
Plan validation using Petri net theory and schema validation.
Simplified for PM4Py 2.8.x interface.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from jsonschema import ValidationError, validate
from pm4py.analysis import check_is_workflow_net, check_soundness
from pm4py.objects.petri_net.obj import Marking, PetriNet
from pm4py.objects.petri_net.utils.petri_utils import add_arc_from_to

from .registry import EventRegistry, ToolRegistry
from .schema import PLAN_JSONSCHEMA, PlanModel


class PlanValidationError(Exception):
    """Raised when plan validation fails"""

    pass


@dataclass
class ValidationResult:
    """Result of a single validation check"""

    validator_name: str
    success: bool
    error_message: Optional[str] = None


class Validator:
    """Base class for plan validators"""

    def __init__(self, name: str, description: str, can_run_parallel: bool = True):
        self.name = name
        self.description = description
        self.can_run_parallel = can_run_parallel

    def validate(self, plan: Dict[str, Any]) -> ValidationResult:
        """
        Validate the plan and return result.

        Args:
            plan: Plan dictionary to validate

        Returns:
            ValidationResult with success status and optional error message
        """
        try:
            self._validate_impl(plan)
            return ValidationResult(self.name, True)
        except PlanValidationError as e:
            return ValidationResult(self.name, False, str(e))
        except Exception as e:
            return ValidationResult(self.name, False, f"Unexpected error: {str(e)}")

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        """Override this method to implement validation logic"""
        raise NotImplementedError


class JsonSchemaValidator(Validator):
    """Validates plan against JSON schema"""

    def __init__(self):
        super().__init__(
            name="json_schema",
            description="Validates plan structure against JSON schema",
            can_run_parallel=True,
        )

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        try:
            validate(instance=plan, schema=PLAN_JSONSCHEMA)
        except ValidationError as e:
            raise PlanValidationError(f"JSON Schema validation failed: {str(e)}")


class ExternalEventValidator(Validator):
    """Validates external events against registry"""

    def __init__(self):
        super().__init__(
            name="external_events",
            description="Validates external events against event registry",
            can_run_parallel=True,
        )

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        # Get only truly external events (those with non-None kind in registry)
        external_events = {}
        for name, meta in EventRegistry.items():
            if meta.get("kind") is not None:
                external_events[name] = meta

        for evt in plan["events"]:
            name = evt["name"]

            if name in external_events:
                # External event - must match registry kind
                expected_kind = external_events[name]["kind"]
                actual_kind = evt.get("kind")

                if actual_kind != expected_kind:
                    raise PlanValidationError(
                        f"Kind mismatch for external event {name}: "
                        f"expected '{expected_kind}', got '{actual_kind}'"
                    )
            else:
                # Internal event - must NOT specify kind/schedule
                if evt.get("kind") or evt.get("schedule"):
                    raise PlanValidationError(
                        f"Internal event {name} should not specify 'kind' or 'schedule'"
                    )


class ToolValidator(Validator):
    """Validates tools/actions against registry"""

    def __init__(self):
        super().__init__(
            name="tools",
            description="Validates tools and actions against tool registry",
            can_run_parallel=True,
        )

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        tools = ToolRegistry.load()

        for step in plan["steps"]:
            action = step["action"]
            meta = tools.get(action)

            if meta is None:
                raise PlanValidationError(f"Unknown action: {action}")

            # Check required arguments
            required_args = set(meta["inputs"])
            provided_args = set(step["args"])
            missing_args = required_args - provided_args

            if missing_args:
                raise PlanValidationError(
                    f"Step '{step['name']}' missing required arguments: {missing_args}"
                )


class PetriNetValidator(Validator):
    """Validates Petri net properties"""

    def __init__(self):
        super().__init__(
            name="petri_net",
            description="Validates workflow structure using Petri net analysis",
            can_run_parallel=False,  # Petri net analysis might not be thread-safe
        )

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        try:
            net, initial_marking, final_marking = self._build_petri_net_with_markings(
                plan
            )

            # Debug information
            debug_info = self._get_debug_info(net, initial_marking, final_marking, plan)

            # Check if it's a workflow net
            is_wf_net = check_is_workflow_net(net)
            if not is_wf_net:
                raise PlanValidationError(
                    f"Plan does not form a valid workflow net.\n"
                    f"Debug info:\n{debug_info}\n"
                    f"Workflow net requirements:\n"
                    f"- Must have exactly one source place (no incoming arcs)\n"
                    f"- Must have exactly one sink place (no outgoing arcs)\n"
                    f"- Every node must be on a path from source to sink"
                )

            # Check soundness with proper markings
            try:
                is_sound = check_soundness(net, initial_marking, final_marking)
                if not is_sound:
                    raise PlanValidationError(
                        f"Petri net is not sound.\n"
                        f"Debug info:\n{debug_info}\n"
                        f"Soundness requirements:\n"
                        f"- Net must be safe (at most one token per place)\n"
                        f"- Net must be live (no deadlocks)\n"
                        f"- Net must be bounded (finite state space)"
                    )
            except Exception as e:
                raise PlanValidationError(
                    f"Soundness check failed with error: {str(e)}\n"
                    f"Debug info:\n{debug_info}"
                )

            # For acyclic plans, check for cycles (simplified check)
            if plan["graph_type"] == "acyclic":
                self._check_acyclicity(net)

        except PlanValidationError:
            raise
        except Exception as e:
            # Provide debug info even for unexpected errors
            try:
                net, initial_marking, final_marking = (
                    self._build_petri_net_with_markings(plan)
                )
                debug_info = self._get_debug_info(
                    net, initial_marking, final_marking, plan
                )
                raise PlanValidationError(
                    f"Petri net validation failed with unexpected error: {str(e)}\n"
                    f"Debug info:\n{debug_info}"
                )
            except:
                raise PlanValidationError(f"Petri net validation failed: {str(e)}")

    def _get_debug_info(
        self,
        net: PetriNet,
        initial_marking: Marking,
        final_marking: Marking,
        plan: Dict[str, Any],
    ) -> str:
        """Generate detailed debug information about the Petri net structure"""
        info = []

        info.append(f"=== PETRI NET DEBUG INFO ===")
        info.append(f"Plan: {plan['plan_name']} ({plan['graph_type']})")
        info.append(f"Places: {len(net.places)}")
        info.append(f"Transitions: {len(net.transitions)}")
        info.append(
            f"Arcs: {len([arc for place in net.places for arc in place.in_arcs]) + len([arc for place in net.places for arc in place.out_arcs])}"
        )

        info.append(f"\n--- PLACES ---")
        for place in net.places:
            in_arcs = len(place.in_arcs)
            out_arcs = len(place.out_arcs)
            initial_tokens = initial_marking.get(place, 0)
            final_tokens = final_marking.get(place, 0)

            place_type = "UNKNOWN"
            if in_arcs == 0 and out_arcs > 0:
                place_type = "SOURCE"
            elif in_arcs > 0 and out_arcs == 0:
                place_type = "SINK"
            elif in_arcs > 0 and out_arcs > 0:
                place_type = "INTERMEDIATE"
            elif in_arcs == 0 and out_arcs == 0:
                place_type = "ISOLATED"

            info.append(
                f"  {place.name}: {place_type} (in:{in_arcs}, out:{out_arcs}, init:{initial_tokens}, final:{final_tokens})"
            )

        info.append(f"\n--- TRANSITIONS ---")
        for transition in net.transitions:
            in_arcs = len(transition.in_arcs)
            out_arcs = len(transition.out_arcs)

            input_places = [arc.source.name for arc in transition.in_arcs]
            output_places = [arc.target.name for arc in transition.out_arcs]

            info.append(
                f"  {transition.name}: in:{in_arcs} {input_places} -> out:{out_arcs} {output_places}"
            )

        info.append(f"\n--- MARKINGS ---")
        info.append(
            f"Initial marking: {[(place.name, tokens) for place, tokens in initial_marking.items()]}"
        )
        info.append(
            f"Final marking: {[(place.name, tokens) for place, tokens in final_marking.items()]}"
        )

        # Analyze workflow net properties
        info.append(f"\n--- WORKFLOW NET ANALYSIS ---")
        source_places = [
            p for p in net.places if len(p.in_arcs) == 0 and len(p.out_arcs) > 0
        ]
        sink_places = [
            p for p in net.places if len(p.in_arcs) > 0 and len(p.out_arcs) == 0
        ]
        isolated_places = [
            p for p in net.places if len(p.in_arcs) == 0 and len(p.out_arcs) == 0
        ]

        info.append(
            f"Source places (no input, has output): {[p.name for p in source_places]}"
        )
        info.append(
            f"Sink places (has input, no output): {[p.name for p in sink_places]}"
        )
        info.append(
            f"Isolated places (no input, no output): {[p.name for p in isolated_places]}"
        )

        # Check workflow net requirements
        info.append(f"\n--- WORKFLOW NET REQUIREMENTS ---")
        info.append(
            f"✓ Exactly 1 source place required: {len(source_places) == 1} (found {len(source_places)})"
        )
        info.append(
            f"✓ Exactly 1 sink place required: {len(sink_places) == 1} (found {len(sink_places)})"
        )
        info.append(
            f"✓ No isolated places allowed: {len(isolated_places) == 0} (found {len(isolated_places)})"
        )

        # Analyze plan structure
        info.append(f"\n--- PLAN STRUCTURE ANALYSIS ---")
        external_events = [evt for evt in plan["events"] if evt.get("kind")]
        internal_events = [evt for evt in plan["events"] if not evt.get("kind")]

        info.append(f"External events: {[evt['name'] for evt in external_events]}")
        info.append(f"Internal events: {[evt['name'] for evt in internal_events]}")

        # Check event connectivity
        all_consumed_events = set()
        all_emitted_events = set()
        for step in plan["steps"]:
            all_consumed_events.update(step["on"])
            all_emitted_events.update(step.get("emits", []))

        info.append(f"Events consumed by steps: {sorted(all_consumed_events)}")
        info.append(f"Events emitted by steps: {sorted(all_emitted_events)}")

        orphaned_events = (
            set(evt["name"] for evt in plan["events"])
            - all_consumed_events
            - all_emitted_events
        )
        if orphaned_events:
            info.append(
                f"⚠️  Orphaned events (not consumed or emitted): {sorted(orphaned_events)}"
            )

        return "\n".join(info)

    def _build_petri_net(self, plan: Dict[str, Any]) -> PetriNet:
        """Build Petri net from plan"""
        net, _, _ = self._build_petri_net_with_markings(plan)
        return net

    def _build_petri_net_with_markings(
        self, plan: Dict[str, Any]
    ) -> Tuple[PetriNet, Marking, Marking]:
        """Build Petri net from plan with initial and final markings"""
        net = PetriNet(plan["plan_name"])

        # Create places only for events that are actually used in steps
        places = {}
        all_used_events = set()
        
        # Collect all events used in steps
        for step in plan["steps"]:
            all_used_events.update(step["on"])
            all_used_events.update(step.get("emits", []))
        
        # Only create places for events that are actually used
        for evt in plan["events"]:
            name = evt["name"]
            if name in all_used_events:
                place = PetriNet.Place(name)
                places[name] = place
                net.places.add(place)

        # Create places for internal events (emitted by steps)
        for step in plan["steps"]:
            for emitted_event in step.get("emits", []):
                if emitted_event not in places:
                    place = PetriNet.Place(emitted_event)
                    places[emitted_event] = place
                    net.places.add(place)

        # Create transitions for steps and connect with arcs
        for step in plan["steps"]:
            transition = PetriNet.Transition(step["name"], step["name"])
            net.transitions.add(transition)

            # Input arcs (from events to transition)
            for event_name in step["on"]:
                if event_name in places:
                    add_arc_from_to(places[event_name], transition, net)
                else:
                    raise PlanValidationError(
                        f"Step '{step['name']}' references unknown event: {event_name}"
                    )

            # Output arcs (from transition to emitted events)
            for event_name in step.get("emits", []):
                add_arc_from_to(transition, places[event_name], net)

        # Create initial and final markings
        initial_marking = Marking()
        final_marking = Marking()

        # Find external events (those with 'kind' specified) for initial marking
        external_events = set()
        for evt in plan["events"]:
            if evt.get("kind"):
                external_events.add(evt["name"])

        # Initial marking: put tokens in external event places
        for event_name in external_events:
            if event_name in places:
                initial_marking[places[event_name]] = 1

        # Final marking: put tokens in places that are not consumed by any transition
        # (i.e., final events that are emitted but not consumed)
        all_consumed_events = set()
        all_emitted_events = set()

        for step in plan["steps"]:
            all_consumed_events.update(step["on"])
            all_emitted_events.update(step.get("emits", []))

        # Final events are those that are emitted but never consumed
        final_events = all_emitted_events - all_consumed_events

        for event_name in final_events:
            if event_name in places:
                final_marking[places[event_name]] = 1

        # If no final events found, create a virtual sink place for workflow completion
        if not final_marking:
            # Add a special sink place for the workflow
            sink_place = PetriNet.Place("workflow_complete")
            places["workflow_complete"] = sink_place
            net.places.add(sink_place)
            final_marking[sink_place] = 1

            # Connect steps that don't emit events to the sink
            for step in plan["steps"]:
                if not step.get("emits", []):
                    # Find the transition for this step
                    for transition in net.transitions:
                        if transition.name == step["name"]:
                            add_arc_from_to(transition, sink_place, net)
                            break

        return net, initial_marking, final_marking

    def _check_acyclicity(self, net: PetriNet) -> None:
        """Simple cycle detection for acyclic plans"""
        # Build adjacency list
        graph = {}
        for transition in net.transitions:
            graph[transition.name] = []

            # Find transitions that can follow this one
            for out_arc in transition.out_arcs:
                place = out_arc.target
                for in_arc in place.out_arcs:
                    next_transition = in_arc.target
                    if isinstance(next_transition, PetriNet.Transition):
                        graph[transition.name].append(next_transition.name)

        # DFS cycle detection
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if has_cycle(neighbor):
                    return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    raise PlanValidationError("Cycle detected in acyclic plan")


class PydanticValidator(Validator):
    """Validates plan using Pydantic model for type safety"""

    def __init__(self):
        super().__init__(
            name="pydantic",
            description="Validates plan types and structure using Pydantic model",
            can_run_parallel=True,
        )

    def _validate_impl(self, plan: Dict[str, Any]) -> None:
        try:
            PlanModel.model_validate(plan)
        except Exception as e:
            raise PlanValidationError(f"Pydantic validation failed: {str(e)}")


# Registry of all available validators
DEFAULT_VALIDATORS = [
    JsonSchemaValidator(),
    ExternalEventValidator(),
    ToolValidator(),
    PetriNetValidator(),
    PydanticValidator(),
]


def run_validations_parallel(
    plan: Dict[str, Any],
    validators: Optional[List[Validator]] = None,
    max_workers: int = 4,
) -> List[ValidationResult]:
    """
    Run validations in parallel where possible.

    Args:
        plan: Plan dictionary to validate
        validators: List of validators to run (defaults to DEFAULT_VALIDATORS)
        max_workers: Maximum number of parallel workers

    Returns:
        List of ValidationResult objects
    """
    if validators is None:
        validators = DEFAULT_VALIDATORS

    # Separate parallel and sequential validators
    parallel_validators = [v for v in validators if v.can_run_parallel]
    sequential_validators = [v for v in validators if not v.can_run_parallel]

    results = []

    # Run parallel validators
    if parallel_validators:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all parallel validation tasks
            future_to_validator = {
                executor.submit(validator.validate, plan): validator
                for validator in parallel_validators
            }

            # Collect results as they complete
            for future in as_completed(future_to_validator):
                result = future.result()
                results.append(result)

    # Run sequential validators
    for validator in sequential_validators:
        result = validator.validate(plan)
        results.append(result)

    return results


def validate_plan_new(
    plan: Dict[str, Any],
    validators: Optional[List[Validator]] = None,
    parallel: bool = True,
    max_workers: int = 4,
) -> None:
    """
    New comprehensive plan validation with parallel execution.

    Args:
        plan: Plan dictionary to validate
        validators: List of validators to run (defaults to DEFAULT_VALIDATORS)
        parallel: Whether to run validations in parallel where possible
        max_workers: Maximum number of parallel workers

    Raises:
        PlanValidationError: If any validation fails
    """
    if validators is None:
        validators = DEFAULT_VALIDATORS

    if parallel:
        results = run_validations_parallel(plan, validators, max_workers)
    else:
        # Run sequentially
        results = [validator.validate(plan) for validator in validators]

    # Check for failures
    failed_results = [r for r in results if not r.success]

    if failed_results:
        error_messages = []
        for result in failed_results:
            error_messages.append(f"{result.validator_name}: {result.error_message}")

        raise PlanValidationError(
            f"Plan validation failed:\n" + "\n".join(error_messages)
        )


# Legacy functions for backward compatibility
def _jsonschema_check(plan: Dict[str, Any]) -> None:
    """Validate plan against JSON schema"""
    validator = JsonSchemaValidator()
    result = validator.validate(plan)
    if not result.success:
        raise PlanValidationError(result.error_message)


def _external_event_check(plan: Dict[str, Any]) -> None:
    """Validate external events against registry"""
    validator = ExternalEventValidator()
    result = validator.validate(plan)
    if not result.success:
        raise PlanValidationError(result.error_message)


def _tool_check(plan: Dict[str, Any]) -> None:
    """Validate tools/actions against registry"""
    validator = ToolValidator()
    result = validator.validate(plan)
    if not result.success:
        raise PlanValidationError(result.error_message)


def _build_petri_net(plan: Dict[str, Any]) -> PetriNet:
    """Build Petri net from plan"""
    validator = PetriNetValidator()
    return validator._build_petri_net(plan)


def _petri_net_check(plan: Dict[str, Any]) -> None:
    """Validate Petri net properties"""
    validator = PetriNetValidator()
    result = validator.validate(plan)
    if not result.success:
        raise PlanValidationError(result.error_message)


def _check_acyclicity(net: PetriNet) -> None:
    """Simple cycle detection for acyclic plans"""
    validator = PetriNetValidator()
    validator._check_acyclicity(net)


def validate_plan(plan: Dict[str, Any]) -> None:
    """
    Comprehensive plan validation (legacy interface).

    Args:
        plan: Plan dictionary to validate

    Raises:
        PlanValidationError: If validation fails
    """
    # Use the new validation system but maintain the same interface
    validate_plan_new(plan, parallel=True)
