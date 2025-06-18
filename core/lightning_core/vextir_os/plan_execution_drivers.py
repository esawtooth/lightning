"""
Plan execution drivers that handle plan setup and lifecycle management.
Plans are registered as first-class applications in Vextir OS.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..planner.schema import PlanModel
from .drivers import (
    Driver,
    DriverManifest,
    DriverType,
    ResourceSpec,
    ToolDriver,
    driver,
)
from .events import Event
from .orchestration_drivers import SchedulerDriver
from .registries import PlanSpec, get_plan_registry


@driver(
    "plan_executor",
    DriverType.TOOL,
    capabilities=["plan.execute", "plan.setup", "plan.lifecycle"],
    name="Plan Executor Driver",
    description="Handles plan execution, setup, and lifecycle management",
)
class PlanExecutorDriver(ToolDriver):
    """Handles plan execution and setup events from the planner"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.active_plans: Dict[str, Dict[str, Any]] = {}
        self.scheduler_driver = None
        self.plan_registry = get_plan_registry()  # Access to plan registry

    def get_capabilities(self) -> List[str]:
        return ["plan.execute", "plan.setup", "plan.lifecycle", "cron.configure"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=60)

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle plan execution events"""
        output_events = []

        if event.type == "plan.execute":
            # Execute a plan
            plan_data = event.metadata.get("plan")
            if plan_data:
                execution_events = await self._execute_plan(plan_data, event.user_id)
                output_events.extend(execution_events)

        elif event.type == "plan.setup":
            # Set up a plan (register it, configure cron jobs, etc.)
            plan_data = event.metadata.get("plan")
            if plan_data:
                setup_events = await self._setup_plan(plan_data, event.user_id)
                output_events.extend(setup_events)

        elif event.type == "cron.configure" or event.type == "event.cron.configured":
            # Handle cron configuration from plans
            cron_events = await self._handle_cron_configuration(event)
            output_events.extend(cron_events)

        elif event.type == "plan.trigger":
            # Trigger a specific plan
            plan_id = event.metadata.get("plan_id")
            trigger_event = event.metadata.get("trigger_event", "event.manual.trigger")

            if plan_id and plan_id in self.active_plans:
                trigger_events = await self._trigger_plan(
                    plan_id, trigger_event, event.user_id
                )
                output_events.extend(trigger_events)

        elif event.type == "plan.status":
            # Get plan status
            plan_id = event.metadata.get("plan_id")
            status = await self._get_plan_status(plan_id, event.user_id)

            status_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.status.response",
                user_id=event.user_id,
                metadata={"plan_id": plan_id, "status": status},
            )
            output_events.append(status_event)

        elif event.type == "plan.register":
            # Register a plan as a first-class application
            plan_data = event.metadata.get("plan")
            if plan_data:
                register_events = await self._register_plan_as_application(
                    plan_data, event.user_id
                )
                output_events.extend(register_events)

        elif event.type == "plan.unregister":
            # Unregister a plan application
            plan_id = event.metadata.get("plan_id")
            if plan_id:
                unregister_events = await self._unregister_plan_application(
                    plan_id, event.user_id
                )
                output_events.extend(unregister_events)

        return output_events

    async def _execute_plan(
        self, plan_data: Dict[str, Any], user_id: str
    ) -> List[Event]:
        """Execute a plan by setting it up and triggering initial events"""
        output_events = []

        try:
            plan_id = plan_data.get("plan_name")
            logging.info(f"Executing plan: {plan_id} for user {user_id}")

            # First set up the plan
            setup_events = await self._setup_plan(plan_data, user_id)
            output_events.extend(setup_events)

            # Find external events that should trigger the plan
            external_events = [
                evt
                for evt in plan_data.get("events", [])
                if evt.get("kind")  # External events have 'kind'
            ]

            # Trigger the plan with external events
            for ext_event in external_events:
                trigger_events = await self._trigger_plan(
                    plan_id, ext_event["name"], user_id
                )
                output_events.extend(trigger_events)

            # Create plan execution started event
            started_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.execution.started",
                user_id=user_id,
                metadata={
                    "plan_id": plan_id,
                    "external_events": [evt["name"] for evt in external_events],
                },
            )
            output_events.append(started_event)

        except Exception as e:
            logging.error(f"Failed to execute plan: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.execution.failed",
                user_id=user_id,
                metadata={
                    "plan_id": plan_data.get("plan_name", "unknown"),
                    "error": str(e),
                },
            )
            output_events.append(error_event)

        return output_events

    async def _setup_plan(self, plan_data: Dict[str, Any], user_id: str) -> List[Event]:
        """Set up a plan for execution"""
        output_events = []

        try:
            plan_id = plan_data.get("plan_name")

            # Register the plan
            self.active_plans[plan_id] = {
                "plan_data": plan_data,
                "user_id": user_id,
                "status": "active",
                "created_at": datetime.utcnow().isoformat(),
                "last_triggered": None,
            }

            logging.info(f"Set up plan: {plan_id} for user {user_id}")

            # Schedule the plan's time-based events with the scheduler drivers
            schedule_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.schedule",
                user_id=user_id,
                metadata={"plan": plan_data},
            )
            output_events.append(schedule_event)

            # Create plan setup completed event
            setup_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.setup.completed",
                user_id=user_id,
                metadata={
                    "plan_id": plan_id,
                    "steps_count": len(plan_data.get("steps", [])),
                    "events_count": len(plan_data.get("events", [])),
                },
            )
            output_events.append(setup_event)

        except Exception as e:
            logging.error(f"Failed to set up plan: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.setup.failed",
                user_id=user_id,
                metadata={
                    "plan_id": plan_data.get("plan_name", "unknown"),
                    "error": str(e),
                },
            )
            output_events.append(error_event)

        return output_events

    async def _handle_cron_configuration(self, event: Event) -> List[Event]:
        """Handle cron configuration events from plans"""
        output_events = []

        try:
            # Extract cron configuration from event
            if event.type == "cron.configure":
                plan_id = event.metadata.get("plan_id")
                cron_expression = event.metadata.get("cron_expression")
                description = event.metadata.get("description", "")
            else:  # event.cron.configured
                # This might come from a plan step that emits cron.configured
                plan_id = event.metadata.get("plan_id")
                cron_expression = event.metadata.get("cron_expression")
                description = event.metadata.get("description", "")

            if plan_id and cron_expression:
                # Create a schedule event for the scheduler driver
                schedule_event = Event(
                    timestamp=datetime.utcnow(),
                    source="PlanExecutorDriver",
                    type="schedule.create",
                    user_id=event.user_id,
                    metadata={
                        "cron": cron_expression,
                        "event": {
                            "type": f"event.cron.{plan_id.replace('-', '_')}",
                            "metadata": {
                                "plan_id": plan_id,
                                "triggered_by": "cron",
                                "description": description,
                            },
                        },
                    },
                )
                output_events.append(schedule_event)

                logging.info(
                    f"Configured cron job for plan {plan_id}: {cron_expression}"
                )

                # Create confirmation event
                confirm_event = Event(
                    timestamp=datetime.utcnow(),
                    source="PlanExecutorDriver",
                    type="cron.configuration.completed",
                    user_id=event.user_id,
                    metadata={
                        "plan_id": plan_id,
                        "cron_expression": cron_expression,
                        "description": description,
                    },
                )
                output_events.append(confirm_event)

        except Exception as e:
            logging.error(f"Failed to handle cron configuration: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="cron.configuration.failed",
                user_id=event.user_id,
                metadata={"error": str(e)},
            )
            output_events.append(error_event)

        return output_events

    async def _trigger_plan(
        self, plan_id: str, trigger_event: str, user_id: str
    ) -> List[Event]:
        """Trigger a plan with a specific event"""
        output_events = []

        try:
            if plan_id not in self.active_plans:
                logging.warning(f"Plan {plan_id} not found for triggering")
                return output_events

            plan_info = self.active_plans[plan_id]
            plan_data = plan_info["plan_data"]

            # Update last triggered time
            plan_info["last_triggered"] = datetime.utcnow().isoformat()

            # Find steps that are triggered by this event
            triggered_steps = [
                step
                for step in plan_data.get("steps", [])
                if trigger_event in step.get("on", [])
            ]

            # Create events for each triggered step
            for step in triggered_steps:
                step_event = Event(
                    timestamp=datetime.utcnow(),
                    source="PlanExecutorDriver",
                    type="plan.step.execute",
                    user_id=user_id,
                    metadata={
                        "plan_id": plan_id,
                        "step_name": step["name"],
                        "action": step["action"],
                        "args": step.get("args", {}),
                        "emits": step.get("emits", []),
                        "trigger_event": trigger_event,
                    },
                )
                output_events.append(step_event)

            logging.info(
                f"Triggered {len(triggered_steps)} steps for plan {plan_id} with event {trigger_event}"
            )

            # Create plan triggered event
            triggered_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.triggered",
                user_id=user_id,
                metadata={
                    "plan_id": plan_id,
                    "trigger_event": trigger_event,
                    "steps_triggered": len(triggered_steps),
                },
            )
            output_events.append(triggered_event)

        except Exception as e:
            logging.error(f"Failed to trigger plan {plan_id}: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.trigger.failed",
                user_id=user_id,
                metadata={
                    "plan_id": plan_id,
                    "trigger_event": trigger_event,
                    "error": str(e),
                },
            )
            output_events.append(error_event)

        return output_events

    async def _get_plan_status(self, plan_id: str, user_id: str) -> Dict[str, Any]:
        """Get status of a plan"""
        if plan_id not in self.active_plans:
            return {"status": "not_found"}

        plan_info = self.active_plans[plan_id]
        return {
            "status": plan_info["status"],
            "created_at": plan_info["created_at"],
            "last_triggered": plan_info["last_triggered"],
            "user_id": plan_info["user_id"],
            "plan_name": plan_info["plan_data"].get("plan_name"),
            "steps_count": len(plan_info["plan_data"].get("steps", [])),
            "events_count": len(plan_info["plan_data"].get("events", [])),
        }

    async def _register_plan_as_application(
        self, plan_data: Dict[str, Any], user_id: str
    ) -> List[Event]:
        """Register a plan as a first-class application in Vextir OS"""
        output_events = []

        try:
            plan_id = plan_data.get("plan_name")

            # Create PlanModel from JSON data
            plan_model = PlanModel(**plan_data)

            # Extract event triggers from plan
            event_triggers = []
            for event in plan_model.events:
                event_triggers.append(event.name)

            # Determine capabilities based on plan steps
            capabilities = []
            for step in plan_model.steps:
                capabilities.append(f"action.{step.action}")
                for emitted in step.emits:
                    capabilities.append(f"emit.{emitted}")

            # Create PlanSpec
            plan_spec = PlanSpec(
                id=plan_id,
                name=plan_model.plan_name,
                description=plan_model.description or f"Plan: {plan_model.plan_name}",
                plan_definition=plan_model,
                event_triggers=event_triggers,
                capabilities=capabilities,
                version="1.0.0",
                author=user_id,
                enabled=True,
                metadata={
                    "user_id": user_id,
                    "created_at": datetime.utcnow().isoformat(),
                },
            )

            # Register in plan registry
            self.plan_registry.register_plan(plan_spec)

            # Also maintain active plans for backward compatibility
            self.active_plans[plan_id] = {
                "plan_data": plan_data,
                "user_id": user_id,
                "status": "registered",
                "created_at": datetime.utcnow().isoformat(),
                "last_triggered": None,
                "plan_spec": plan_spec,
            }

            logging.info(f"Registered plan {plan_id} as first-class application")

            # Create registration success event
            success_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.registered",
                user_id=user_id,
                metadata={
                    "plan_id": plan_id,
                    "plan_name": plan_model.plan_name,
                    "event_triggers": event_triggers,
                    "capabilities": capabilities,
                },
            )
            output_events.append(success_event)

        except Exception as e:
            logging.error(f"Failed to register plan as application: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.registration.failed",
                user_id=user_id,
                metadata={
                    "plan_id": plan_data.get("plan_name", "unknown"),
                    "error": str(e),
                },
            )
            output_events.append(error_event)

        return output_events

    async def _unregister_plan_application(
        self, plan_id: str, user_id: str
    ) -> List[Event]:
        """Unregister a plan application"""
        output_events = []

        try:
            # Remove from plan registry
            if self.plan_registry.unregister_plan(plan_id):
                # Remove from active plans
                if plan_id in self.active_plans:
                    del self.active_plans[plan_id]

                logging.info(f"Unregistered plan application: {plan_id}")

                success_event = Event(
                    timestamp=datetime.utcnow(),
                    source="PlanExecutorDriver",
                    type="plan.unregistered",
                    user_id=user_id,
                    metadata={"plan_id": plan_id},
                )
                output_events.append(success_event)
            else:
                # Plan not found
                not_found_event = Event(
                    timestamp=datetime.utcnow(),
                    source="PlanExecutorDriver",
                    type="plan.unregistration.failed",
                    user_id=user_id,
                    metadata={"plan_id": plan_id, "error": "Plan not found"},
                )
                output_events.append(not_found_event)

        except Exception as e:
            logging.error(f"Failed to unregister plan application {plan_id}: {e}")

            error_event = Event(
                timestamp=datetime.utcnow(),
                source="PlanExecutorDriver",
                type="plan.unregistration.failed",
                user_id=user_id,
                metadata={"plan_id": plan_id, "error": str(e)},
            )
            output_events.append(error_event)

        return output_events


# Function to register plan execution drivers
async def register_plan_execution_drivers():
    """Register all plan execution drivers with the system"""
    from .drivers import get_driver_registry

    registry = get_driver_registry()

    # Register drivers
    drivers = [(PlanExecutorDriver._vextir_manifest, PlanExecutorDriver)]

    for manifest, driver_class in drivers:
        try:
            await registry.register_driver(manifest, driver_class)
            logging.info(f"Registered plan execution driver: {manifest.id}")
        except Exception as e:
            logging.error(f"Failed to register driver {manifest.id}: {e}")


class PlanApplicationManager:
    """Manager for plan applications in Vextir OS"""

    def __init__(self):
        self.plan_registry = get_plan_registry()

    async def register_plan_from_json(
        self, plan_json: Dict[str, Any], user_id: str = "system"
    ) -> str:
        """Register a plan from JSON definition as a first-class application"""
        from .event_bus import get_event_bus

        event_bus = get_event_bus()

        # Create plan registration event
        register_event = Event(
            timestamp=datetime.utcnow(),
            source="PlanApplicationManager",
            type="plan.register",
            user_id=user_id,
            metadata={"plan": plan_json},
        )

        # Emit the event to be handled by PlanExecutorDriver
        await event_bus.emit(register_event)
        return plan_json.get("plan_name", "unknown")

    async def unregister_plan(self, plan_id: str, user_id: str = "system"):
        """Unregister a plan application"""
        from .event_bus import get_event_bus

        event_bus = get_event_bus()

        # Create plan unregistration event
        unregister_event = Event(
            timestamp=datetime.utcnow(),
            source="PlanApplicationManager",
            type="plan.unregister",
            user_id=user_id,
            metadata={"plan_id": plan_id},
        )

        await event_bus.emit(unregister_event)

    def list_plan_applications(self) -> List[Dict[str, Any]]:
        """List all registered plan applications"""
        plans = self.plan_registry.list_plans()
        return [
            {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "version": plan.version,
                "author": plan.author,
                "enabled": plan.enabled,
                "event_triggers": plan.event_triggers,
                "capabilities": plan.capabilities,
                "metadata": plan.metadata,
            }
            for plan in plans
        ]

    def get_plan_application(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific plan application"""
        plan = self.plan_registry.get_plan(plan_id)
        if plan:
            return {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "version": plan.version,
                "author": plan.author,
                "enabled": plan.enabled,
                "event_triggers": plan.event_triggers,
                "capabilities": plan.capabilities,
                "plan_definition": plan.plan_definition.dict(),
                "metadata": plan.metadata,
            }
        return None

    def get_plans_by_event_trigger(self, event_type: str) -> List[PlanSpec]:
        """Get plans that should be triggered by a specific event type"""
        return self.plan_registry.get_plans_by_event(event_type)


# Global plan application manager
_global_plan_manager: Optional[PlanApplicationManager] = None


def get_plan_application_manager() -> PlanApplicationManager:
    """Get global plan application manager"""
    global _global_plan_manager
    if _global_plan_manager is None:
        _global_plan_manager = PlanApplicationManager()
    return _global_plan_manager
