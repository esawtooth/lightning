"""
Instruction processor for automatic plan generation.

This module handles instruction-related events and automatically generates
plans using the Lightning planner when instructions are created or updated.
"""

import asyncio
import logging
from typing import Any, Dict

from ..abstractions import EventMessage
from ..planner.planner import call_planner_llm
from ..planner.storage import PlanStore

logger = logging.getLogger(__name__)


class InstructionProcessor:
    """Processes instruction events and generates plans."""
    
    def __init__(self, plan_store: PlanStore = None):
        self.plan_store = plan_store or PlanStore()
        
    async def handle_instruction_created(self, event: EventMessage):
        """Handle instruction.created events by generating a plan."""
        try:
            instruction_data = event.data.get("instruction")
            instruction_id = event.data.get("instruction_id")
            user_id = event.metadata.get("userID", "default")
            
            if not instruction_data:
                logger.error("No instruction data in instruction.created event")
                return
                
            logger.info(f"Processing instruction.created event for {instruction_id}")
            
            # Generate natural language instruction for the planner
            plan_instruction = self._build_plan_instruction(instruction_data)
            
            # Call the planner to generate a plan
            logger.info(f"Generating plan for instruction: {plan_instruction}")
            plan_json = await call_planner_llm(
                instruction=plan_instruction,
                registry_subset={},
                user_id=user_id
            )
            
            # Add instruction metadata to the plan
            plan_json["instruction_id"] = instruction_id
            plan_json["instruction_name"] = instruction_data.get("name", "Unknown")
            
            # Store the generated plan
            plan_id = self.plan_store.save(user_id, plan_json)
            
            logger.info(f"Generated and stored plan {plan_id} for instruction {instruction_id} (user: {user_id})")
            logger.info(f"Plan store now has {len(self.plan_store.mem) if hasattr(self.plan_store, 'mem') else 'unknown'} plans")
            logger.info(f"Plan store instance in processor: {id(self.plan_store)}")
            
            # Optionally publish a plan.generated event
            # This could be used to notify other parts of the system
            # that a plan was generated from an instruction
            
        except Exception as e:
            logger.error(f"Failed to process instruction.created event: {e}", exc_info=True)
            # Store the error in the plan errors storage
            try:
                # Import the storage to update error state
                from lightning_core.api.main import plan_errors_storage
                plan_errors_storage[instruction_id] = str(e)
            except Exception as se:
                logger.error(f"Failed to store plan generation error: {se}")
    
    async def handle_instruction_updated(self, event: EventMessage):
        """Handle instruction.updated events by regenerating plans if needed."""
        try:
            instruction_data = event.data.get("instruction")
            instruction_id = event.data.get("instruction_id")
            previous_data = event.data.get("previous")
            user_id = event.metadata.get("userID", "default")
            
            if not instruction_data:
                logger.error("No instruction data in instruction.updated event")
                return
                
            # Check if the instruction trigger or action changed significantly
            if self._should_regenerate_plan(instruction_data, previous_data):
                logger.info(f"Regenerating plan for updated instruction {instruction_id}")
                
                # Generate new plan instruction
                plan_instruction = self._build_plan_instruction(instruction_data)
                
                # Call the planner to generate a new plan
                plan_json = await call_planner_llm(
                    instruction=plan_instruction,
                    registry_subset={},
                    user_id=user_id
                )
                
                # Add instruction metadata to the plan
                plan_json["instruction_id"] = instruction_id
                plan_json["instruction_name"] = instruction_data.get("name", "Unknown")
                
                # Store the regenerated plan
                plan_id = self.plan_store.save(user_id, plan_json)
                
                logger.info(f"Regenerated and stored plan {plan_id} for instruction {instruction_id}")
            else:
                logger.info(f"Instruction {instruction_id} changes don't require plan regeneration")
                
        except Exception as e:
            logger.error(f"Failed to process instruction.updated event: {e}", exc_info=True)
    
    def _build_plan_instruction(self, instruction_data: Dict[str, Any]) -> str:
        """Build a natural language instruction for the planner based on the instruction data."""
        name = instruction_data.get("name", "Unnamed instruction")
        description = instruction_data.get("description", "")
        trigger = instruction_data.get("trigger", {})
        action = instruction_data.get("action", {})
        
        # Extract trigger information
        event_type = trigger.get("event_type", "unknown")
        providers = trigger.get("providers", [])
        conditions = trigger.get("conditions", {})
        
        # Extract action information
        action_type = action.get("type", "unknown")
        action_config = action.get("config", {})
        
        # Build a comprehensive instruction
        instruction_parts = [
            f"Create a workflow plan for: {name}",
        ]
        
        if description:
            instruction_parts.append(f"Description: {description}")
        
        # Trigger description
        trigger_desc = f"When a {event_type} event occurs"
        if providers:
            trigger_desc += f" from {', '.join(providers)}"
        if conditions:
            content_filters = conditions.get("content_filters", {})
            if content_filters.get("subject_contains"):
                subject_keywords = content_filters["subject_contains"]
                trigger_desc += f" with subject containing: {', '.join(subject_keywords)}"
        
        instruction_parts.append(f"Trigger: {trigger_desc}")
        
        # Action description
        action_desc = f"Execute {action_type}"
        if action_type == "update_context_summary":
            context_key = action_config.get("context_key", "")
            synthesis_prompt = action_config.get("synthesis_prompt", "")
            action_desc += f" for context key '{context_key}'"
            if synthesis_prompt:
                action_desc += f" using prompt: {synthesis_prompt}"
        elif action_type == "send_email":
            email_config = action_config.get("email", {})
            to_address = email_config.get("to", "")
            subject = email_config.get("subject", "")
            action_desc += f" to {to_address} with subject '{subject}'"
        elif action_type == "conseil_task":
            prompt = action_config.get("prompt", "")
            complexity = action_config.get("complexity", "simple")
            action_desc += f" with {complexity} complexity"
            if prompt:
                action_desc += f" and prompt: {prompt}"
        
        instruction_parts.append(f"Action: {action_desc}")
        
        # Add plan type guidance
        instruction_parts.append("This should be a reactive workflow that can handle multiple instances of the trigger event.")
        
        return "\n".join(instruction_parts)
    
    def _should_regenerate_plan(self, current: Dict[str, Any], previous: Dict[str, Any]) -> bool:
        """Determine if plan should be regenerated based on changes."""
        if not previous:
            return True
            
        # Check if trigger changed
        if current.get("trigger") != previous.get("trigger"):
            return True
            
        # Check if action changed
        if current.get("action") != previous.get("action"):
            return True
            
        # Check if enabled status changed to enabled (might want to regenerate)
        if current.get("enabled") and not previous.get("enabled"):
            return True
            
        return False


# Global processor instance
_processor = None

def get_instruction_processor(plan_store=None) -> InstructionProcessor:
    """Get the global instruction processor instance."""
    global _processor
    if _processor is None:
        _processor = InstructionProcessor(plan_store)
    elif plan_store and _processor.plan_store != plan_store:
        # Update the plan store if a new one is provided
        _processor.plan_store = plan_store
    return _processor


async def setup_instruction_event_handlers(runtime):
    """Set up event handlers for instruction processing."""
    processor = get_instruction_processor()
    
    # Subscribe to instruction events
    await runtime.event_bus.subscribe("instruction.created", processor.handle_instruction_created)
    await runtime.event_bus.subscribe("instruction.updated", processor.handle_instruction_updated)
    
    logger.info("Instruction event handlers set up successfully")