"""
Orchestration drivers that replace instruction processing, scheduling, and task management Azure Functions
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from croniter import croniter
from typing import Any, Dict, List, Optional

from azure.cosmos import CosmosClient, PartitionKey
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event, EmailEvent, CalendarEvent, ContextUpdateEvent, InstructionEvent, WorkerTaskEvent
from .drivers import Driver, AgentDriver, ToolDriver, DriverManifest, DriverType, ResourceSpec, driver
from .registries import get_model_registry, get_tool_registry


@driver("instruction_engine", DriverType.AGENT,
        capabilities=["instruction.process", "workflow.execute", "automation.trigger"],
        name="Instruction Engine Driver",
        description="Processes user instructions and triggers automated workflows")
class InstructionEngineDriver(AgentDriver):
    """Replaces InstructionProcessor Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.cosmos_conn = os.environ.get("COSMOS_CONNECTION")
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.instruction_container = os.environ.get("INSTRUCTION_CONTAINER", "instructions")
        self.servicebus_conn = os.environ.get("SERVICEBUS_CONNECTION")
        self.servicebus_queue = os.environ.get("SERVICEBUS_QUEUE")
        
        # Initialize Cosmos client
        self._client = CosmosClient.from_connection_string(self.cosmos_conn) if self.cosmos_conn else None
        self._db = self._client.create_database_if_not_exists(self.cosmos_db) if self._client else None
        self._instruction_container = self._db.create_container_if_not_exists(
            id=self.instruction_container, partition_key=PartitionKey(path="/pk")
        ) if self._db else None
        
        # Initialize service bus client
        self._sb_client = ServiceBusClient.from_connection_string(self.servicebus_conn) if self.servicebus_conn else None
        
        self.system_prompt = """
You are an instruction processing agent that analyzes events and executes user-defined automation rules.
You can:
- Match events to instruction triggers
- Execute complex workflows
- Create context updates
- Delegate tasks to specialized agents
- Send notifications and communications
"""
    
    def get_capabilities(self) -> List[str]:
        return ["instruction.process", "workflow.execute", "automation.trigger"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=1024, timeout_seconds=120)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle instruction processing events"""
        output_events = []
        
        # Skip processing instruction events to avoid loops
        if event.type.startswith("instruction.") or event.type.startswith("context."):
            return output_events
        
        # Get user instructions
        instructions = await self._get_user_instructions(event.user_id)
        if not instructions:
            logging.info(f"No instructions found for user {event.user_id}, discarding event {event.type}")
            return output_events
        
        # Process matching instructions
        matched_count = 0
        
        for instruction in instructions:
            if await self._match_event_to_instruction(event, instruction):
                matched_count += 1
                logging.info(f"Event {event.type} matched instruction {instruction['name']} for user {event.user_id}")
                
                action_events = await self._execute_instruction_action(event, instruction)
                output_events.extend(action_events)
        
        if matched_count == 0:
            logging.info(f"Event {event.type} did not match any instructions for user {event.user_id}, discarding")
        else:
            logging.info(f"Event {event.type} matched {matched_count} instructions for user {event.user_id}")
        
        return output_events
    
    async def _get_user_instructions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all enabled instructions for a user"""
        if not self._instruction_container:
            return []
        
        try:
            items = list(await asyncio.to_thread(
                self._instruction_container.query_items,
                query="SELECT * FROM c WHERE c.pk=@user_id AND c.enabled=true",
                parameters=[{"name": "@user_id", "value": user_id}],
                enable_cross_partition_query=True,
            ))
            return items
        except Exception as e:
            logging.error(f"Failed to get instructions for user {user_id}: {e}")
            return []
    
    async def _match_event_to_instruction(self, event: Event, instruction: Dict[str, Any]) -> bool:
        """Check if an event matches an instruction's trigger conditions"""
        trigger = instruction.get("trigger", {})
        
        # Check event type match
        expected_type = trigger.get("event_type")
        if not expected_type:
            return False
        
        # Support wildcard matching
        if expected_type == "*" or event.type == expected_type:
            pass
        elif expected_type.endswith(".*") and event.type.startswith(expected_type[:-1]):
            pass
        else:
            return False
        
        # Check provider match for email/calendar events
        if hasattr(event, 'provider') and trigger.get("providers"):
            if event.provider not in trigger["providers"]:
                return False
        
        # Check additional conditions
        conditions = trigger.get("conditions", {})
        
        # Time-based conditions
        if "time_range" in conditions:
            time_range = conditions["time_range"]
            current_hour = datetime.utcnow().hour
            if "start_hour" in time_range and current_hour < time_range["start_hour"]:
                return False
            if "end_hour" in time_range and current_hour > time_range["end_hour"]:
                return False
        
        # Content-based conditions (for email events)
        if isinstance(event, EmailEvent) and "content_filters" in conditions:
            email_data = event.email_data
            content_filters = conditions["content_filters"]
            
            # Subject filters
            if "subject_contains" in content_filters:
                subject = email_data.get("subject", "").lower()
                for keyword in content_filters["subject_contains"]:
                    if keyword.lower() not in subject:
                        return False
            
            # Sender filters
            if "from_contains" in content_filters:
                sender = email_data.get("from", "").lower()
                for keyword in content_filters["from_contains"]:
                    if keyword.lower() not in sender:
                        return False
        
        return True
    
    async def _execute_instruction_action(self, event: Event, instruction: Dict[str, Any]) -> List[Event]:
        """Execute the action defined in an instruction and return resulting events"""
        action = instruction.get("action", {})
        action_type = action.get("type")
        config = action.get("config", {})
        
        result_events = []
        
        try:
            if action_type == "update_context_summary":
                # Create a context update event
                context_key = config.get("context_key", "general_summary")
                synthesis_prompt = config.get("synthesis_prompt", "Update the running summary with key information from this event.")
                
                # Extract content from the event
                content = await self._extract_event_content(event)
                
                context_event = ContextUpdateEvent(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="context.update",
                    user_id=event.user_id,
                    context_key=context_key,
                    update_operation="synthesize",
                    content=content,
                    synthesis_prompt=synthesis_prompt,
                    history=event.history + [event.to_dict()],
                )
                result_events.append(context_event)
            
            elif action_type == "create_task":
                # Create a worker task event
                task_description = config.get("task_template", "Process event: {event_type}")
                task_description = task_description.format(
                    event_type=event.type,
                    user_id=event.user_id,
                    timestamp=event.timestamp.isoformat()
                )
                
                task_event = WorkerTaskEvent(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="worker.task",
                    user_id=event.user_id,
                    task=task_description,
                    history=event.history + [event.to_dict()],
                )
                result_events.append(task_event)
            
            elif action_type == "conseil_task":
                # Delegate complex task to Conseil worker with full context
                task_prompt = config.get("prompt", "Process this event intelligently.")
                complexity = config.get("complexity", "complex")
                fallback_action = config.get("fallback_action")
                
                # Create enriched task prompt with event context
                enriched_prompt = f"""
{task_prompt}

Event Context:
- Type: {event.type}
- Source: {event.source}
- Timestamp: {event.timestamp.isoformat()}
- User ID: {event.user_id}

Event Data:
{await self._extract_event_content(event)}

Full Event Metadata:
{json.dumps(event.metadata, indent=2)}

Instructions:
1. Analyze the event data above
2. Execute the requested task: {task_prompt}
3. Use the context hub CLI to update relevant context if needed
4. Create appropriate events via service bus for any actions needed
5. Provide a summary of what was accomplished

Available tools:
- contexthub CLI for reading/writing context
- Service bus for creating events (email.send, notification.send, task.create, etc.)
- Full bash access for any system operations needed
"""
                
                # Create WorkerTaskEvent for Conseil
                conseil_event = WorkerTaskEvent(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="worker.task",
                    user_id=event.user_id,
                    task=enriched_prompt,
                    metadata={
                        "agent": "conseil",
                        "instruction_name": instruction.get("name", "Unknown"),
                        "complexity": complexity,
                        "trigger_event": event.to_dict(),
                        "fallback_action": fallback_action
                    },
                    history=event.history + [event.to_dict()],
                )
                result_events.append(conseil_event)
                
                logging.info(f"Created Conseil task for instruction '{instruction.get('name')}' with complexity '{complexity}'")
            
            elif action_type == "send_notification":
                # Create a simple notification event (fast path)
                notification_config = config.get("notification", {})
                
                notification_event = Event(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="notification.send",
                    user_id=event.user_id,
                    metadata={
                        "title": notification_config.get("title", f"Event: {event.type}"),
                        "message": notification_config.get("message", "An event was processed").format(
                            event_type=event.type,
                            timestamp=event.timestamp.isoformat(),
                            **event.metadata
                        ),
                        "priority": notification_config.get("priority", "normal"),
                        "channel": notification_config.get("channel", "default")
                    },
                    history=event.history + [event.to_dict()],
                )
                result_events.append(notification_event)
            
            elif action_type == "send_email":
                # Create an email event to send a notification
                email_config = config.get("email", {})
                
                email_event = EmailEvent(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="email.send",
                    user_id=event.user_id,
                    operation="send",
                    provider=email_config.get("provider", "gmail"),
                    email_data={
                        "to": email_config.get("to", ""),
                        "subject": email_config.get("subject", f"Notification: {event.type}"),
                        "body": email_config.get("body_template", "Event processed: {event_type}").format(
                            event_type=event.type,
                            timestamp=event.timestamp.isoformat()
                        )
                    },
                    history=event.history + [event.to_dict()],
                )
                result_events.append(email_event)
            
            elif action_type == "schedule_action":
                # Create a scheduled event
                schedule_config = config.get("schedule", {})
                
                scheduled_event = Event(
                    timestamp=datetime.utcnow(),
                    source="InstructionEngineDriver",
                    type="schedule.create",
                    user_id=event.user_id,
                    metadata={
                        "cron": schedule_config.get("cron"),
                        "event": schedule_config.get("event_template", {}),
                    },
                    history=event.history + [event.to_dict()],
                )
                result_events.append(scheduled_event)
            
            # Update instruction execution count
            await self._update_instruction_execution(event.user_id, instruction["id"])
            
        except Exception as e:
            logging.error(f"Failed to execute instruction action {action_type}: {e}")
        
        return result_events
    
    async def _extract_event_content(self, event: Event) -> str:
        """Extract meaningful content from an event for context synthesis"""
        if isinstance(event, EmailEvent):
            email_data = event.email_data
            return f"Email from {email_data.get('from', 'unknown')}: {email_data.get('subject', 'No subject')} - {email_data.get('body', '')[:500]}"
        
        elif isinstance(event, CalendarEvent):
            calendar_data = event.calendar_data
            return f"Calendar event: {calendar_data.get('title', 'No title')} at {calendar_data.get('start_time', 'unknown time')} - {calendar_data.get('description', '')[:500]}"
        
        else:
            return f"Event of type {event.type} from {event.source}"
    
    async def _update_instruction_execution(self, user_id: str, instruction_id: str):
        """Update instruction execution count"""
        if not self._instruction_container:
            return
        
        try:
            item = await asyncio.to_thread(self._instruction_container.read_item, instruction_id, partition_key=user_id)
            item["execution_count"] = item.get("execution_count", 0) + 1
            item["last_executed"] = datetime.utcnow().isoformat()
            await asyncio.to_thread(self._instruction_container.upsert_item, item)
        except Exception as e:
            logging.error(f"Failed to update instruction execution count: {e}")


@driver("task_monitor", DriverType.TOOL,
        capabilities=["task.monitor", "task.status", "task.metrics"],
        name="Task Monitor Driver",
        description="Monitors task execution and provides status updates")
class TaskMonitorDriver(ToolDriver):
    """Replaces TaskMonitor Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.cosmos_conn = os.environ.get("COSMOS_CONNECTION")
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.task_container = os.environ.get("TASK_CONTAINER", "tasks")
        
        # Initialize Cosmos client
        self._client = CosmosClient.from_connection_string(self.cosmos_conn) if self.cosmos_conn else None
        self._db = self._client.create_database_if_not_exists(self.cosmos_db) if self._client else None
        self._task_container = self._db.create_container_if_not_exists(
            id=self.task_container, partition_key=PartitionKey(path="/pk")
        ) if self._db else None
    
    def get_capabilities(self) -> List[str]:
        return ["task.monitor", "task.status", "task.metrics"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle task monitoring events"""
        output_events = []
        
        if isinstance(event, WorkerTaskEvent):
            # Monitor worker task
            task_id = await self._create_task_record(event)
            
            status_event = Event(
                timestamp=datetime.utcnow(),
                source="TaskMonitorDriver",
                type="task.created",
                user_id=event.user_id,
                metadata={
                    "task_id": task_id,
                    "task_type": "worker_task",
                    "status": "created"
                }
            )
            output_events.append(status_event)
        
        elif event.type == "task.status.update":
            # Update task status
            task_id = event.metadata.get("task_id")
            status = event.metadata.get("status")
            
            await self._update_task_status(task_id, status, event.user_id)
            
            status_event = Event(
                timestamp=datetime.utcnow(),
                source="TaskMonitorDriver",
                type="task.status.updated",
                user_id=event.user_id,
                metadata={
                    "task_id": task_id,
                    "status": status
                }
            )
            output_events.append(status_event)
        
        elif event.type == "task.metrics.request":
            # Get task metrics
            metrics = await self._get_task_metrics(event.user_id)
            
            metrics_event = Event(
                timestamp=datetime.utcnow(),
                source="TaskMonitorDriver",
                type="task.metrics.response",
                user_id=event.user_id,
                metadata={"metrics": metrics}
            )
            output_events.append(metrics_event)
        
        return output_events
    
    async def _create_task_record(self, task_event: WorkerTaskEvent) -> str:
        """Create a task record in the database"""
        if not self._task_container:
            return "unknown"
        
        try:
            task_id = f"task_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{task_event.user_id}"
            
            task_record = {
                "id": task_id,
                "pk": task_event.user_id,
                "task_type": "worker_task",
                "task_description": task_event.task[:1000],  # Truncate for storage
                "status": "created",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "metadata": task_event.metadata
            }
            
            await asyncio.to_thread(self._task_container.create_item, task_record)
            return task_id
        except Exception as e:
            logging.error(f"Failed to create task record: {e}")
            return "unknown"
    
    async def _update_task_status(self, task_id: str, status: str, user_id: str):
        """Update task status in the database"""
        if not self._task_container:
            return
        
        try:
            task_record = await asyncio.to_thread(self._task_container.read_item, task_id, partition_key=user_id)
            task_record["status"] = status
            task_record["updated_at"] = datetime.utcnow().isoformat()
            
            if status in ["completed", "failed"]:
                task_record["completed_at"] = datetime.utcnow().isoformat()
            
            await asyncio.to_thread(self._task_container.upsert_item, task_record)
        except Exception as e:
            logging.error(f"Failed to update task status: {e}")
    
    async def _get_task_metrics(self, user_id: str) -> Dict[str, Any]:
        """Get task metrics for a user"""
        if not self._task_container:
            return {}
        
        try:
            # Get task counts by status
            items = list(await asyncio.to_thread(
                self._task_container.query_items,
                query="SELECT c.status, COUNT(1) as count FROM c WHERE c.pk=@user_id GROUP BY c.status",
                parameters=[{"name": "@user_id", "value": user_id}],
                enable_cross_partition_query=True,
            ))
            
            metrics = {
                "total_tasks": 0,
                "by_status": {},
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            for item in items:
                status = item.get("status", "unknown")
                count = item.get("count", 0)
                metrics["by_status"][status] = count
                metrics["total_tasks"] += count
            
            return metrics
        except Exception as e:
            logging.error(f"Failed to get task metrics: {e}")
            return {}


@driver("scheduler", DriverType.TOOL,
        capabilities=["schedule.create", "schedule.update", "schedule.delete", "schedule.trigger"],
        name="Scheduler Driver",
        description="Manages scheduled events and triggers")
class SchedulerDriver(ToolDriver):
    """Replaces Scheduler Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.cosmos_conn = os.environ.get("COSMOS_CONNECTION")
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.schedule_container = os.environ.get("SCHEDULE_CONTAINER", "schedules")
        
        # Initialize Cosmos client
        self._client = CosmosClient.from_connection_string(self.cosmos_conn) if self.cosmos_conn else None
        self._db = self._client.create_database_if_not_exists(self.cosmos_db) if self._client else None
        self._schedule_container = self._db.create_container_if_not_exists(
            id=self.schedule_container, partition_key=PartitionKey(path="/pk")
        ) if self._db else None
    
    def get_capabilities(self) -> List[str]:
        return ["schedule.create", "schedule.update", "schedule.delete", "schedule.trigger"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle scheduling events"""
        output_events = []
        
        if event.type == "schedule.create":
            # Create a new scheduled event
            schedule_id = await self._create_schedule(event)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="SchedulerDriver",
                type="schedule.created",
                user_id=event.user_id,
                metadata={
                    "schedule_id": schedule_id,
                    "cron": event.metadata.get("cron"),
                    "event_template": event.metadata.get("event")
                }
            )
            output_events.append(result_event)
        
        elif event.type == "schedule.update":
            # Update an existing schedule
            schedule_id = event.metadata.get("schedule_id")
            await self._update_schedule(schedule_id, event.user_id, event.metadata)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="SchedulerDriver",
                type="schedule.updated",
                user_id=event.user_id,
                metadata={"schedule_id": schedule_id}
            )
            output_events.append(result_event)
        
        elif event.type == "schedule.delete":
            # Delete a schedule
            schedule_id = event.metadata.get("schedule_id")
            await self._delete_schedule(schedule_id, event.user_id)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="SchedulerDriver",
                type="schedule.deleted",
                user_id=event.user_id,
                metadata={"schedule_id": schedule_id}
            )
            output_events.append(result_event)
        
        elif event.type == "schedule.trigger":
            # Trigger scheduled events (called by timer)
            triggered_events = await self._trigger_scheduled_events()
            output_events.extend(triggered_events)
        
        return output_events
    
    async def _create_schedule(self, event: Event) -> str:
        """Create a new schedule record"""
        if not self._schedule_container:
            return "unknown"
        
        try:
            schedule_id = f"schedule_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{event.user_id}"
            
            schedule_record = {
                "id": schedule_id,
                "pk": event.user_id,
                "cron": event.metadata.get("cron"),
                "event_template": event.metadata.get("event", {}),
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "last_triggered": None,
                "next_trigger": self._calculate_next_trigger(event.metadata.get("cron"))
            }
            
            await asyncio.to_thread(self._schedule_container.create_item, schedule_record)
            return schedule_id
        except Exception as e:
            logging.error(f"Failed to create schedule: {e}")
            return "unknown"
    
    async def _update_schedule(self, schedule_id: str, user_id: str, updates: Dict[str, Any]):
        """Update an existing schedule"""
        if not self._schedule_container:
            return
        
        try:
            schedule_record = await asyncio.to_thread(self._schedule_container.read_item, schedule_id, partition_key=user_id)
            
            # Update fields
            if "cron" in updates:
                schedule_record["cron"] = updates["cron"]
                schedule_record["next_trigger"] = self._calculate_next_trigger(updates["cron"])
            
            if "event" in updates:
                schedule_record["event_template"] = updates["event"]
            
            if "enabled" in updates:
                schedule_record["enabled"] = updates["enabled"]
            
            schedule_record["updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.to_thread(self._schedule_container.upsert_item, schedule_record)
        except Exception as e:
            logging.error(f"Failed to update schedule: {e}")
    
    async def _delete_schedule(self, schedule_id: str, user_id: str):
        """Delete a schedule"""
        if not self._schedule_container:
            return
        
        try:
            await asyncio.to_thread(self._schedule_container.delete_item, schedule_id, partition_key=user_id)
        except Exception as e:
            logging.error(f"Failed to delete schedule: {e}")
    
    async def _trigger_scheduled_events(self) -> List[Event]:
        """Check for and trigger scheduled events that are due"""
        if not self._schedule_container:
            return []
        
        try:
            current_time = datetime.utcnow().isoformat()
            
            # Query for schedules that are due
            items = list(await asyncio.to_thread(
                self._schedule_container.query_items,
                query="SELECT * FROM c WHERE c.enabled=true AND c.next_trigger <= @current_time",
                parameters=[{"name": "@current_time", "value": current_time}],
                enable_cross_partition_query=True,
            ))
            
            triggered_events = []
            
            for schedule in items:
                try:
                    # Create event from template
                    event_template = schedule.get("event_template", {})
                    
                    triggered_event = Event(
                        timestamp=datetime.utcnow(),
                        source="SchedulerDriver",
                        type=event_template.get("type", "scheduled.event"),
                        user_id=schedule.get("pk"),
                        metadata={
                            **event_template.get("metadata", {}),
                            "schedule_id": schedule.get("id"),
                            "triggered_at": current_time
                        }
                    )
                    
                    triggered_events.append(triggered_event)
                    
                    # Update schedule with next trigger time
                    schedule["last_triggered"] = current_time
                    schedule["next_trigger"] = self._calculate_next_trigger(schedule.get("cron"))
                    schedule["updated_at"] = current_time
                    
                    await asyncio.to_thread(self._schedule_container.upsert_item, schedule)
                    
                except Exception as e:
                    logging.error(f"Failed to trigger schedule {schedule.get('id')}: {e}")
            
            return triggered_events
            
        except Exception as e:
            logging.error(f"Failed to trigger scheduled events: {e}")
            return []
    
    def _calculate_next_trigger(self, cron_expression: str) -> str:
        """Calculate the next trigger time for a cron expression"""
        try:
            return croniter(cron_expression, datetime.utcnow()).get_next(datetime).isoformat()
        except Exception as e:
            logging.error("Invalid cron expression %s: %s", cron_expression, e)
            return (datetime.utcnow() + timedelta(hours=1)).isoformat()


# Function to register all orchestration drivers
async def register_orchestration_drivers():
    """Register all orchestration drivers with the system"""
    from .drivers import get_driver_registry
    
    registry = get_driver_registry()
    
    # Register drivers
    drivers = [
        (InstructionEngineDriver._vextir_manifest, InstructionEngineDriver),
        (TaskMonitorDriver._vextir_manifest, TaskMonitorDriver),
        (SchedulerDriver._vextir_manifest, SchedulerDriver)
    ]
    
    for manifest, driver_class in drivers:
        try:
            await registry.register_driver(manifest, driver_class)
            logging.info(f"Registered orchestration driver: {manifest.id}")
        except Exception as e:
            logging.error(f"Failed to register driver {manifest.id}: {e}")
