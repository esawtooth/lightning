import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event, EmailEvent, CalendarEvent, ContextUpdateEvent, InstructionEvent, WorkerTaskEvent

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
INSTRUCTION_CONTAINER = os.environ.get("INSTRUCTION_CONTAINER", "instructions")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

_client = CosmosClient.from_connection_string(COSMOS_CONN) if COSMOS_CONN else None
_db = _client.create_database_if_not_exists(COSMOS_DB) if _client else None
_instruction_container = _db.create_container_if_not_exists(
    id=INSTRUCTION_CONTAINER, partition_key=PartitionKey(path="/pk")
) if _db else None
_sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN) if SERVICEBUS_CONN else None


def _get_user_instructions(user_id: str) -> List[Dict[str, Any]]:
    """Get all enabled instructions for a user."""
    if not _instruction_container:
        return []
    
    try:
        items = list(_instruction_container.query_items(
            query="SELECT * FROM c WHERE c.pk=@user_id AND c.enabled=true",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        return items
    except Exception as e:
        logging.error(f"Failed to get instructions for user {user_id}: {e}")
        return []


def _match_event_to_instruction(event: Event, instruction: Dict[str, Any]) -> bool:
    """Check if an event matches an instruction's trigger conditions."""
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


def _execute_instruction_action(event: Event, instruction: Dict[str, Any]) -> List[Event]:
    """Execute the action defined in an instruction and return resulting events."""
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
            content = _extract_event_content(event)
            
            context_event = ContextUpdateEvent(
                timestamp=datetime.utcnow(),
                source="InstructionProcessor",
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
                source="InstructionProcessor",
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
{_extract_event_content(event)}

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
                source="InstructionProcessor",
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
                source="InstructionProcessor",
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
                source="InstructionProcessor",
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
                source="InstructionProcessor",
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
        _update_instruction_execution(event.user_id, instruction["id"])
        
    except Exception as e:
        logging.error(f"Failed to execute instruction action {action_type}: {e}")
    
    return result_events


def _extract_event_content(event: Event) -> str:
    """Extract meaningful content from an event for context synthesis."""
    if isinstance(event, EmailEvent):
        email_data = event.email_data
        return f"Email from {email_data.get('from', 'unknown')}: {email_data.get('subject', 'No subject')} - {email_data.get('body', '')[:500]}"
    
    elif isinstance(event, CalendarEvent):
        calendar_data = event.calendar_data
        return f"Calendar event: {calendar_data.get('title', 'No title')} at {calendar_data.get('start_time', 'unknown time')} - {calendar_data.get('description', '')[:500]}"
    
    else:
        return f"Event of type {event.type} from {event.source}"


def _update_instruction_execution(user_id: str, instruction_id: str):
    """Update instruction execution count."""
    if not _instruction_container:
        return
    
    try:
        item = _instruction_container.read_item(instruction_id, partition_key=user_id)
        item["execution_count"] = item.get("execution_count", 0) + 1
        item["last_executed"] = datetime.utcnow().isoformat()
        _instruction_container.upsert_item(item)
    except Exception as e:
        logging.error(f"Failed to update instruction execution count: {e}")


def _publish_events(events: List[Event]):
    """Publish events to the service bus."""
    if not _sb_client or not events:
        return
    
    try:
        with _sb_client:
            sender = _sb_client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
            with sender:
                for event in events:
                    message = ServiceBusMessage(json.dumps(event.to_dict()))
                    message.application_properties = {"topic": event.type}
                    sender.send_messages(message)
                    logging.info(f"Published event {event.type} for user {event.user_id}")
    except Exception as e:
        logging.error(f"Failed to publish events: {e}")


def main(msg: func.ServiceBusMessage) -> None:
    """Main handler for processing events against user instructions."""
    
    if not _instruction_container:
        logging.error("Instruction container not configured")
        return
    
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = Event.from_dict(data)
    except Exception as e:
        logging.error(f"Invalid event: {e}")
        return
    
    # Skip processing instruction events to avoid loops
    if event.type.startswith("instruction.") or event.type.startswith("context."):
        return
    
    # Get user instructions
    instructions = _get_user_instructions(event.user_id)
    if not instructions:
        logging.info(f"No instructions found for user {event.user_id}, discarding event {event.type}")
        return
    
    # Process matching instructions
    result_events = []
    matched_count = 0
    
    for instruction in instructions:
        if _match_event_to_instruction(event, instruction):
            matched_count += 1
            logging.info(f"Event {event.type} matched instruction {instruction['name']} for user {event.user_id}")
            
            action_events = _execute_instruction_action(event, instruction)
            result_events.extend(action_events)
    
    if matched_count == 0:
        logging.info(f"Event {event.type} did not match any instructions for user {event.user_id}, discarding")
    else:
        logging.info(f"Event {event.type} matched {matched_count} instructions for user {event.user_id}")
        
        # Publish resulting events
        if result_events:
            _publish_events(result_events)
