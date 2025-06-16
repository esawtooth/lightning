import json
import time
from typing import Dict, Any

from openai import OpenAI

from .registry import ToolRegistry
from .schema import PLAN_JSONSCHEMA

openai_client = OpenAI()

_SYSTEM_PROMPT = """You are Lightning-Planner, an expert workflow designer.
Return ONE function call 'create_plan' whose argument `plan_json`
conforms to the provided JSON-Schema.  Use the available tools only."""


def _function_spec():
    return {
        "name": "create_plan",
        "description": "Submit a verified plan as JSON",
        "parameters": PLAN_JSONSCHEMA,
    }


def call_planner_llm(
    instruction: str,
    registry_subset: Dict[str, Any],
    max_retries: int = 6,
) -> Dict[str, Any]:
    """Run critic loop until a syntactically valid JSON object is emitted."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "assistant",
            "content": f"AVAILABLE_TOOLS\n{json.dumps(registry_subset, indent=2)}",
        },
        {"role": "user", "content": instruction},
    ]
    for attempt in range(max_retries):
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=messages,
            functions=[_function_spec()],
            function_call="auto",
        )
        call = resp.choices[0].message
        if call.function_call and call.function_call.name == "create_plan":
            try:
                return json.loads(call.function_call.arguments)
            except json.JSONDecodeError as e:
                messages.append(
                    {
                        "role": "system",
                        "content": f"CRITIC: invalid JSON – {e}",
                    }
                )
        else:
            messages.append(
                {"role": "system", "content": "CRITIC: you must call create_plan"}
            )
        time.sleep(1)
    raise RuntimeError("Planner failed to return valid plan_json")
