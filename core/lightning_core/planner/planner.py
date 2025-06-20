# lightning_planner/planner.py
import json
import logging
import textwrap
import time
from typing import Any, Dict, Optional
import asyncio

from .registry import EventRegistry, ToolRegistry
from .schema import PlanModel  # only for post‑validation typing
from .validator import PlanValidationError, validate_plan

# Import the completions API
from ..llm import get_completions_api, Message, MessageRole

# Default model for planning (can be overridden)
DEFAULT_PLANNER_MODEL = "o3-mini"  # Use o3-mini as default for planning


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
        • Return a JSON object with two fields:
          - "plan": The complete workflow plan following the schema
          - "summary": A 2-3 sentence natural language summary of what the plan does
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
# Main functions
# ---------------------------------------------------------------------------
async def call_planner_llm(
    instruction: str,
    registry_subset: Dict[str, Any],  # kept for API symmetry
    max_retries: int = 4,
    seconds_between: float = 0.8,
    model: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call the planner LLM to generate a workflow plan.
    
    Args:
        instruction: User instruction for the plan
        registry_subset: Registry subset (kept for API compatibility)
        max_retries: Maximum number of retry attempts
        seconds_between: Seconds to wait between retries
        model: Model to use (defaults to DEFAULT_PLANNER_MODEL)
        user_id: User ID for usage tracking
        
    Returns:
        Valid plan dictionary
    """
    api = get_completions_api()
    model = model or DEFAULT_PLANNER_MODEL
    
    system_prompt = _make_system_prompt()
    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        Message(role=MessageRole.USER, content=instruction),
    ]

    for attempt in range(1, max_retries + 1):
        try:
            # Use the completions API with JSON response format
            # Don't use temperature for o3-mini model
            create_params = {
                "model": model,
                "messages": messages,
                "user_id": user_id,
                "response_format": {"type": "json_object"},
            }
            
            # Only add temperature if not using o3-mini
            if model != "o3-mini":
                create_params["temperature"] = 0.7
                
            resp = await api.create(**create_params)
            
            # Parse the JSON response
            response_json = json.loads(resp.choices[0].message.content)
            
            # Extract plan and summary
            if isinstance(response_json, dict) and "plan" in response_json:
                plan_json = response_json["plan"]
                summary = response_json.get("summary", "No summary provided.")
            else:
                # Backwards compatibility: if response is just the plan
                plan_json = response_json
                summary = "No summary provided."

            # Validate the plan
            validate_plan(plan_json)
            
            # Add summary to the plan metadata
            plan_json["summary"] = summary
            
            return plan_json  # ✅ passes on this attempt
            
        except PlanValidationError as e:
            logging.warning("Attempt %d failed: %s", attempt, e)
            messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content=f"CRITIC: {e}\nPlease re‑emit a corrected plan.",
                )
            )
            await asyncio.sleep(seconds_between)
        except Exception as e:
            logging.error(f"Error in planner attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(seconds_between)

    raise RuntimeError(
        f"Planner could not produce a valid plan in {max_retries} attempts."
    )


# Synchronous wrapper for backward compatibility
def call_planner_llm_sync(
    instruction: str,
    registry_subset: Dict[str, Any] = None,
    max_retries: int = 4,
    seconds_between: float = 0.8,
    model: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper for call_planner_llm"""
    return asyncio.run(
        call_planner_llm(
            instruction=instruction,
            registry_subset=registry_subset or {},
            max_retries=max_retries,
            seconds_between=seconds_between,
            model=model,
            user_id=user_id,
        )
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


async def replan_with_critique(
    original_plan: Dict[str, Any],
    user_critique: str,
    original_instruction: str,
    max_retries: int = 4,
    seconds_between: float = 0.8,
    model: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a new plan based on user critique of the original plan.
    
    Args:
        original_plan: The original plan that was generated
        user_critique: User's feedback/critique of the plan
        original_instruction: The original instruction used to generate the plan
        max_retries: Maximum number of retry attempts
        seconds_between: Seconds to wait between retries
        model: Model to use (defaults to DEFAULT_PLANNER_MODEL)
        user_id: User ID for usage tracking
        
    Returns:
        New plan dictionary incorporating the user's feedback
    """
    api = get_completions_api()
    model = model or DEFAULT_PLANNER_MODEL
    
    system_prompt = _make_system_prompt()
    
    # Create a message that includes the original plan and critique
    critique_message = f"""Original instruction: {original_instruction}

Original plan generated:
{json.dumps(original_plan, indent=2)}

User feedback/critique:
{user_critique}

Please generate a new plan that addresses the user's feedback while still accomplishing the original goal."""
    
    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        Message(role=MessageRole.USER, content=critique_message),
    ]

    for attempt in range(1, max_retries + 1):
        try:
            # Use the completions API with JSON response format
            create_params = {
                "model": model,
                "messages": messages,
                "user_id": user_id,
                "response_format": {"type": "json_object"},
            }
            
            # Only add temperature if not using o3-mini
            if model != "o3-mini":
                create_params["temperature"] = 0.7
                
            resp = await api.create(**create_params)
            
            # Parse the JSON response
            response_json = json.loads(resp.choices[0].message.content)
            
            # Extract plan and summary
            if isinstance(response_json, dict) and "plan" in response_json:
                plan_json = response_json["plan"]
                summary = response_json.get("summary", "No summary provided.")
            else:
                # Backwards compatibility: if response is just the plan
                plan_json = response_json
                summary = "No summary provided."

            # Validate the plan
            validate_plan(plan_json)
            
            # Add summary and metadata to the plan
            plan_json["summary"] = summary
            plan_json["revised_from"] = original_plan.get("id", "unknown")
            plan_json["revision_reason"] = user_critique
            
            return plan_json  # ✅ passes on this attempt
            
        except PlanValidationError as e:
            logging.warning("Replan attempt %d failed: %s", attempt, e)
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content=f"That plan failed validation: {e}\nPlease fix it.",
                )
            )
            
        except json.JSONDecodeError as e:
            logging.error("JSON decode error in replan attempt %d: %s", attempt, e)
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content="Please return only valid JSON with 'plan' and 'summary' fields.",
                )
            )
            
        except Exception as e:
            logging.error("Error in replan attempt %d: %s", attempt, e)
            if attempt < max_retries:
                await asyncio.sleep(seconds_between)
            else:
                raise

        if attempt < max_retries:
            await asyncio.sleep(seconds_between)
    
    raise Exception(f"Failed to generate valid revised plan after {max_retries} attempts")
