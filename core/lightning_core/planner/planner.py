# lightning_planner/planner.py
import json
import logging
import textwrap
import time
from typing import Any, Dict

import openai
from openai import OpenAI

from .registry import EventRegistry, ToolRegistry
from .schema import PlanModel  # only for post‑validation typing
from .validator import PlanValidationError, validate_plan

# OpenAI client will be initialized when needed
openai_client = None


def _get_openai_client():
    """Get or create OpenAI client"""
    global openai_client
    if openai_client is None:
        openai_client = OpenAI()
    return openai_client


# ---------------------------------------------------------------------------
# Helper to build the *one* system prompt that contains every hard fact
# ---------------------------------------------------------------------------
def _make_system_prompt() -> str:
    # 1. Summarise the schema briefly (full schema is huge → token bomb).
    schema_brief = textwrap.dedent(
        """\
        JSON object with:
        • plan_name          : string
        • graph_type         : "acyclic" | "reactive"
        • events             : array of {name, kind?, schedule?, description?}
        • steps              : array of {name, on[], action, args{}, emits[], guard?}
        All string enums must be lowercase; unknown keys forbidden.
    """
    )

    # 2. Allowed external events
    ext_events = (
        "\n".join(
            f'  - {n}  ({meta["kind"]}, {meta.get("schedule","")})'
            for n, meta in EventRegistry.items()
        )
        or "  - (none yet)"
    )

    # 3. Allowed tools + inputs
    tools_meta = ToolRegistry.load()
    tools_lines = []
    for name, meta in tools_meta.items():
        args = ", ".join(f"{k}:{v}" for k, v in meta["inputs"].items())
        tools_lines.append(f"  - {name}({args})")
    tools = "\n".join(tools_lines)

    rules = textwrap.dedent(
        """\
        Additional rules:
        • You MAY invent new internal events (names must start with "event.").
          They must be produced by some step before they are consumed.
        • You MAY NOT invent new actions—pick only from the tool list.
        • External triggers must be chosen ONLY from the external‑event list.
        • Every step must fire at least once in the normal run.
        • Return *only* JSON, no comments, no markdown.
    """
    )

    return "\n\n".join(
        [
            "You are **Lightning‑Planner**, an expert workflow designer.",
            "Design a Petri‑net workflow plan that obeys the following schema:",
            schema_brief,
            "External events you can use:",
            ext_events,
            "Available actions (tools):",
            tools,
            rules,
        ]
    )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
def call_planner_llm(
    instruction: str,
    registry_subset: Dict[str, Any],  # kept for API symmetry
    max_retries: int = 4,
    seconds_between: float = 0.8,
) -> Dict[str, Any]:

    system_prompt = _make_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    for attempt in range(1, max_retries + 1):
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model="o3", messages=messages, response_format={"type": "json_object"}
        )
        plan_json = json.loads(resp.choices[0].message.content)

        try:
            validate_plan(plan_json)
            return plan_json  # ✅ passes on this attempt
        except PlanValidationError as e:
            logging.warning("Attempt %d failed: %s", attempt, e)
            messages.append(
                {
                    "role": "system",
                    "content": f"CRITIC: {e}\nPlease re‑emit a corrected plan.",
                }
            )
            time.sleep(seconds_between)

    raise RuntimeError(
        f"Planner could not produce a valid plan in {max_retries} attempts."
    )


# ---------------------------------------------------------------------------
# Plan execution functions
# ---------------------------------------------------------------------------
def load_plan(plan_path) -> Dict[str, Any]:
    """Load a plan from file"""
    import json
    from pathlib import Path

    path = Path(plan_path)
    with path.open() as f:
        return json.load(f)


def execute_plan(plan_path, user_id: str = "default") -> Dict[str, Any]:
    """Execute a plan by loading, validating, and emitting execution events"""
    plan = load_plan(plan_path)
    validate_plan(plan)

    print(f"Plan '{plan['plan_name']}' validated successfully!")

    # Emit plan execution event for VextirOS to handle
    execution_event = {
        "type": "plan.execute",
        "user_id": user_id,
        "metadata": {"plan": plan, "source": "planner"},
    }

    # In a real implementation, this would be sent to the event bus
    # For now, we'll return the event that should be emitted
    print("Emitting plan execution event for VextirOS...")
    return execution_event


def setup_plan(plan_path, user_id: str = "default") -> Dict[str, Any]:
    """Set up a plan without executing it (register, configure cron, etc.)"""
    plan = load_plan(plan_path)
    validate_plan(plan)

    print(f"Plan '{plan['plan_name']}' validated successfully!")

    # Emit plan setup event for VextirOS to handle
    setup_event = {
        "type": "plan.setup",
        "user_id": user_id,
        "metadata": {"plan": plan, "source": "planner"},
    }

    print("Emitting plan setup event for VextirOS...")
    return setup_event
