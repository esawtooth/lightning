import logging
from typing import Any, Dict

from .planner import call_planner_llm
from .registry import ToolRegistry
from .storage import PlanStore
from .validator import PlanValidationError, validate_plan

logger = logging.getLogger(__name__)


def create_verified_plan(
    instruction: str, user_id: str, registry_query: str | None = None, **openai_kwargs
) -> Dict[str, Any]:
    """
    High‑level helper:
    1. Retrieve relevant tools.
    2. Ask LLM for plan_json (critic loop inside).
    3. Validate plan structurally.
    4. Persist template, return plan + id.
    """
    subset = (
        ToolRegistry.subset(registry_query or "")
        if registry_query is not None
        else ToolRegistry.load()
    )

    plan_json = call_planner_llm(instruction, subset, **openai_kwargs)

    try:
        validate_plan(plan_json)
    except PlanValidationError as e:
        logger.error("Validation failed after critic loop: %s", e)
        raise

    plan_id = PlanStore().save(user_id, plan_json)
    return {"plan_id": plan_id, "plan": plan_json}
