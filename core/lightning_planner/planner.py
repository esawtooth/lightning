# lightning_planner/planner.py
import openai, json, time, textwrap, logging
from typing import Dict, Any
from openai import OpenAI

from .schema     import PlanModel          # only for post‑validation typing
from .validator  import validate_plan, PlanValidationError
from .registry   import ToolRegistry, EventRegistry

openai_client = OpenAI()

# ---------------------------------------------------------------------------
# Helper to build the *one* system prompt that contains every hard fact
# ---------------------------------------------------------------------------
def _make_system_prompt() -> str:
    # 1. Summarise the schema briefly (full schema is huge → token bomb).
    schema_brief = textwrap.dedent("""\
        JSON object with:
        • plan_name          : string
        • graph_type         : "acyclic" | "reactive"
        • events             : array of {name, kind?, schedule?, description?}
        • steps              : array of {name, on[], action, args{}, emits[], guard?}
        All string enums must be lowercase; unknown keys forbidden.
    """)

    # 2. Allowed external events
    ext_events = "\n".join(
        f'  - {n}  ({meta["kind"]}, {meta.get("schedule","")})'
        for n, meta in EventRegistry.items()
    ) or "  - (none yet)"

    # 3. Allowed tools + inputs
    tools_meta = ToolRegistry.load()
    tools_lines = []
    for name, meta in tools_meta.items():
        args = ", ".join(f'{k}:{v}' for k, v in meta["inputs"].items())
        tools_lines.append(f"  - {name}({args})")
    tools = "\n".join(tools_lines)

    rules = textwrap.dedent("""\
        Additional rules:
        • You MAY invent new internal events (names must start with "event.").
          They must be produced by some step before they are consumed.
        • You MAY NOT invent new actions—pick only from the tool list.
        • External triggers must be chosen ONLY from the external‑event list.
        • Every step must fire at least once in the normal run.
        • Return *only* JSON, no comments, no markdown.
    """)

    return "\n\n".join([
        "You are **Lightning‑Planner**, an expert workflow designer.",
        "Design a Petri‑net workflow plan that obeys the following schema:",
        schema_brief,
        "External events you can use:",
        ext_events,
        "Available actions (tools):",
        tools,
        rules,
    ])


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
def call_planner_llm(
    instruction:      str,
    registry_subset:  Dict[str, Any],      # kept for API symmetry
    max_retries:      int  = 4,
    seconds_between:  float = 0.8,
) -> Dict[str, Any]:

    system_prompt = _make_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": instruction},
    ]

    for attempt in range(1, max_retries + 1):
        resp = openai_client.chat.completions.create(
            model="o3",
            messages=messages,
            response_format={"type": "json_object"}
        )
        plan_json = json.loads(resp.choices[0].message.content)

        try:
            validate_plan(plan_json)
            return plan_json        # ✅ passes on this attempt
        except PlanValidationError as e:
            logging.warning("Attempt %d failed: %s", attempt, e)
            messages.append(
                {
                    "role":    "system",
                    "content": f"CRITIC: {e}\nPlease re‑emit a corrected plan."
                }
            )
            time.sleep(seconds_between)

    raise RuntimeError(
        f"Planner could not produce a valid plan in {max_retries} attempts."
)
