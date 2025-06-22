"""
Lightning Core API - Main FastAPI application

This provides REST API endpoints for the Lightning Core system,
replacing Azure Functions endpoints for local development.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
import uuid
from collections import defaultdict
from typing import List

from lightning_core.abstractions import (
    Document,
    EventMessage,
    ExecutionMode,
    RuntimeConfig,
)
from lightning_core.runtime import get_runtime, initialize_runtime
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_all_drivers,
)
from lightning_core.vextir_os.instruction_processor import setup_instruction_event_handlers
from .context_router import router as context_router
from .chat_persistence import ChatPersistence, ChatThread, ChatMessage, ChatToolCall

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


# Global runtime instance
runtime = None

# Global plan store instance (shared across the application)
plan_store = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, str] = {}  # user_id -> connection_id
        self.pending_responses: Dict[str, str] = {}  # request_id -> connection_id
        self.active_threads: Dict[str, ChatThread] = {}  # connection_id -> ChatThread
        
    async def connect(self, websocket: WebSocket, connection_id: str, user_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.user_connections[user_id] = connection_id
        
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        # Remove from user_connections
        for user_id, conn_id in list(self.user_connections.items()):
            if conn_id == connection_id:
                del self.user_connections[user_id]
                
    async def send_message(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            await self.active_connections[connection_id].send_json(message)
            
    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.user_connections:
            connection_id = self.user_connections[user_id]
            await self.send_message(connection_id, message)

manager = ConnectionManager()
chat_persistence = ChatPersistence(os.getenv("CONTEXT_HUB_URL", "http://context-hub:3000"))


# Pydantic models
class EventRequest(BaseModel):
    """Event submission request."""

    type: str = Field(..., description="Event type (e.g., user.action)")
    userID: str = Field(..., description="User ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event metadata")
    source: Optional[str] = Field(default="api", description="Event source")


class EventResponse(BaseModel):
    """Event submission response."""

    success: bool
    event_id: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str = "1.0.0"
    services: Dict[str, str]


class PlanRequest(BaseModel):
    """Plan creation request."""

    description: str = Field(..., description="Natural language plan description")
    userID: str = Field(..., description="User ID")
    plan_type: str = Field(
        default="acyclic", description="Plan type: acyclic or reactive"
    )


class TaskRequest(BaseModel):
    """Task creation request."""

    title: str
    description: Optional[str] = None
    assignedTo: Optional[str] = None
    dueDate: Optional[str] = None
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class InstructionTrigger(BaseModel):
    """Instruction trigger configuration."""
    
    event_type: str
    providers: List[str] = Field(default_factory=list)
    conditions: Optional[Dict[str, Any]] = None


class InstructionAction(BaseModel):
    """Instruction action configuration."""
    
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class InstructionRequest(BaseModel):
    """Instruction creation/update request."""
    
    name: str
    description: Optional[str] = None
    enabled: bool = True
    trigger: InstructionTrigger
    action: InstructionAction


class InstructionResponse(BaseModel):
    """Instruction response."""
    
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    trigger: InstructionTrigger
    action: InstructionAction
    execution_count: int = 0
    last_executed_at: Optional[str] = None
    created_at: str
    updated_at: str


class PlanCritiqueRequest(BaseModel):
    """Plan critique/edit request."""
    
    critique: str
    instruction_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global runtime, plan_store

    logger.info("Starting Lightning Core API...")

    # Configure environment
    configure_drivers_for_environment()

    # Initialize runtime
    config = RuntimeConfig.from_env()
    runtime = await initialize_runtime(config)

    # Initialize drivers
    await initialize_all_drivers()
    
    # Initialize shared plan store
    from lightning_core.planner.storage import PlanStore
    plan_store = PlanStore()
    
    # Pass the shared plan store to instruction processor
    from lightning_core.vextir_os.instruction_processor import get_instruction_processor
    get_instruction_processor(plan_store)

    # Set up instruction event handlers
    await setup_instruction_event_handlers(runtime)

    # Subscribe to chat response events
    async def handle_chat_response(event: EventMessage):
        """Handle chat response events and send to WebSocket clients."""
        if event.event_type == "llm.chat.response":
            request_id = event.metadata.get("request_id")
            user_id = event.metadata.get("userID")
            response_text = event.data.get("response", "")
            
            # Send to the user's WebSocket connection
            if user_id:
                await manager.send_to_user(user_id, {
                    "type": "chat_response",
                    "request_id": request_id,
                    "response": response_text,
                    "usage": event.data.get("usage", {}),
                    "timestamp": event.timestamp.isoformat()
                })
                
                # Update chat thread with assistant response
                if user_id in manager.user_connections:
                    connection_id = manager.user_connections[user_id]
                    if connection_id in manager.active_threads:
                        thread = manager.active_threads[connection_id]
                        thread.messages.append(ChatMessage(
                            role="assistant",
                            content=response_text,
                            metadata={"request_id": request_id}
                        ))
                        thread.updated_at = datetime.utcnow().isoformat()
                        # Save updated thread
                        try:
                            await chat_persistence.save_chat(thread)
                        except Exception as e:
                            logger.error(f"Failed to save chat thread: {e}")
            
            # Also check if we have a pending request
            if request_id and request_id in manager.pending_responses:
                connection_id = manager.pending_responses[request_id]
                await manager.send_message(connection_id, {
                    "type": "chat_response",
                    "request_id": request_id,
                    "response": response_text,
                    "usage": event.data.get("usage", {}),
                    "timestamp": event.timestamp.isoformat()
                })
                del manager.pending_responses[request_id]
    
    # Subscribe to response events
    subscription_id = await runtime.event_bus.subscribe("llm.chat.response", handle_chat_response)
    
    logger.info("Lightning Core API started successfully")

    yield

    # Cleanup
    logger.info("Shutting down Lightning Core API...")
    if runtime:
        await runtime.shutdown()
    logger.info("Lightning Core API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Lightning Core API",
    description="Local API for Lightning Core OS",
    version="1.0.0",
    lifespan=lifespan,
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with API prefix
app.include_router(context_router, prefix="/api")


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services = {
        "api": "healthy",
        "storage": "unknown",
        "event_bus": "unknown",
        "context_hub": "unknown",
    }

    # Check storage
    try:
        if runtime and await runtime.storage.container_exists("health_check"):
            services["storage"] = "healthy"
        else:
            services["storage"] = "healthy"  # Container doesn't need to exist
    except Exception:
        services["storage"] = "unhealthy"

    # Check event bus
    try:
        if runtime and runtime._event_bus and runtime._event_bus._running:
            services["event_bus"] = "healthy"
    except Exception:
        services["event_bus"] = "unhealthy"

    # Check context hub (would need actual check)
    context_hub_url = os.getenv("CONTEXT_HUB_URL", "http://localhost:3000")
    services["context_hub"] = "unknown"  # Would implement actual health check

    overall_status = (
        "healthy"
        if all(s == "healthy" or s == "unknown" for s in services.values())
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        services=services,
    )


# Event endpoints
@app.post("/api/events", response_model=EventResponse)
async def submit_event(event_req: EventRequest):
    """Submit an event for processing."""
    try:
        # Create event message
        event = EventMessage(
            event_type=event_req.type,
            data=event_req.data,
            metadata={
                **event_req.metadata,
                "source": event_req.source,
                "userID": event_req.userID,
                "submitted_via": "api",
            },
        )

        # Publish event
        await runtime.publish_event(event)

        return EventResponse(
            success=True,
            event_id=event.id,
            message=f"Event {event.event_type} submitted successfully",
        )

    except Exception as e:
        logger.error(f"Failed to submit event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/types")
async def get_event_types():
    """Get supported event types."""
    # This would come from driver registry in full implementation
    return {
        "external": [
            "email.received",
            "email.sent",
            "calendar.event.created",
            "calendar.event.updated",
            "calendar.reminder",
            "slack.message",
            "teams.message",
            "github.push",
            "github.pull_request",
            "github.issue",
            "file.uploaded",
            "webhook.received"
        ],
        "internal": [
            "task.created",
            "task.completed",
            "plan.executed",
            "instruction.triggered"
        ],
        "time_based": [
            "schedule.cron",
            "schedule.interval",
            "manual.trigger"
        ]
    }


# Plan endpoints
@app.post("/api/plans")
async def create_plan(plan_req: PlanRequest, request: Request):
    """Create a new plan from natural language description."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Import planner modules
        from lightning_core.planner.planner import call_planner_llm
        
        # Use the global plan store
        global plan_store
        if not plan_store:
            from lightning_core.planner.storage import PlanStore
            plan_store = PlanStore()
        
        # Generate plan using the planner
        logger.info(f"Generating plan for user {user_id}: {plan_req.description}")
        plan_json = await call_planner_llm(
            instruction=plan_req.description,
            registry_subset={},
            user_id=user_id
        )
        
        # Store the plan
        plan_id = plan_store.save(user_id, plan_json)
        
        logger.info(f"Generated and stored plan {plan_id}")
        
        return {
            "success": True,
            "plan_id": plan_id,
            "message": "Plan created successfully",
            "plan": {
                **plan_json,
                "id": plan_id,
                "status": "generated",
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Failed to create plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plans/instruction/{instruction_id}")
async def get_plan_by_instruction(instruction_id: str, request: Request):
    """Get the latest plan for a specific instruction."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Check if this instruction has a plan generation error stored
        if instruction_id in plan_errors_storage and plan_errors_storage[instruction_id]:
            return {
                "error": True,
                "error_message": plan_errors_storage[instruction_id],
                "instruction_id": instruction_id
            }
        
        # Use the global plan store
        global plan_store
        if not plan_store:
            from lightning_core.planner.storage import PlanStore
            plan_store = PlanStore()
        
        # Search for plans that have this instruction_id
        # The PlanStore uses a simple in-memory dictionary
        if hasattr(plan_store, 'mem'):
            logger.info(f"Searching for plans for instruction {instruction_id}, user {user_id}")
            logger.info(f"Total plans in store: {len(plan_store.mem)}")
            logger.info(f"Plan store instance: {id(plan_store)}")
            
            # Find all plans for this user
            user_plans = []
            for plan_id, plan_record in plan_store.mem.items():
                logger.debug(f"Checking plan {plan_id}: user={plan_record.get('pk')}, instruction_id={plan_record.get('plan', {}).get('instruction_id')}")
                if plan_record.get('pk') == user_id:
                    plan = plan_record.get('plan', {})
                    # Check if this plan is for the requested instruction
                    if plan.get('instruction_id') == instruction_id:
                        plan['id'] = plan_id
                        # Handle created_at which might be a string already
                        created_at = plan_record.get('created_at')
                        if isinstance(created_at, str):
                            plan['created_at'] = created_at
                        else:
                            plan['created_at'] = created_at.isoformat() if created_at else datetime.utcnow().isoformat()
                        user_plans.append(plan)
            
            # Return the most recent plan for this instruction
            if user_plans:
                # Sort by created_at if available, otherwise by plan_id
                user_plans.sort(key=lambda p: p.get('created_at', p['id']), reverse=True)
                latest_plan = user_plans[0]
                
                # Transform the plan for the UI
                return {
                    "id": latest_plan['id'],
                    "instruction_id": instruction_id,
                    "summary": latest_plan.get('summary', 'No summary available'),
                    "steps": latest_plan.get('steps', []),
                    "events": latest_plan.get('events', []),
                    "external_triggers": [evt['name'] for evt in latest_plan.get('events', []) if evt.get('kind')],
                    "graph_type": latest_plan.get('graph_type', 'reactive'),
                    "created_at": latest_plan.get('created_at')
                }
        
        # Check for mock plans (for test instructions)
        mock_plans = {
            "test-1": {
                "id": "plan-1",
                "instruction_id": "test-1",
                "summary": "This plan monitors for manual triggers and generates comprehensive plan summaries using AI. When triggered, it analyzes the request context and produces a structured summary document.",
                "steps": [
                    {
                        "name": "Wait for Trigger",
                        "action": "wait_for_manual_trigger",
                        "produces": ["trigger_event"]
                    },
                    {
                        "name": "Analyze Context",
                        "action": "analyze_context",
                        "requires": ["trigger_event"],
                        "produces": ["context_data"]
                    },
                    {
                        "name": "Generate Summary",
                        "action": "generate_plan_summary",
                        "requires": ["context_data"],
                        "produces": ["summary_document"]
                    }
                ],
                "external_triggers": ["manual_trigger"],
                "created_at": datetime.utcnow().isoformat()
            },
            "test-2": {
                "id": "plan-2",
                "instruction_id": "test-2",
                "summary": "This workflow monitors Slack messages for bug reports and automatically creates GitHub issues. It extracts relevant information from the message and formats it appropriately for issue creation.",
                "steps": [
                    {
                        "name": "Monitor Slack",
                        "action": "monitor_slack_messages",
                        "produces": ["slack_message"]
                    },
                    {
                        "name": "Check for Bug Keywords",
                        "action": "check_keywords",
                        "requires": ["slack_message"],
                        "produces": ["bug_report"]
                    },
                    {
                        "name": "Extract Issue Details",
                        "action": "extract_issue_details",
                        "requires": ["bug_report"],
                        "produces": ["issue_data"]
                    },
                    {
                        "name": "Create GitHub Issue",
                        "action": "create_github_issue",
                        "requires": ["issue_data"],
                        "produces": ["github_issue"]
                    }
                ],
                "external_triggers": ["slack.message"],
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        # Return mock plan if exists
        if instruction_id in mock_plans:
            return mock_plans[instruction_id]
        
        # Otherwise return 404
        raise HTTPException(status_code=404, detail="No plans found for this instruction")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get plan for instruction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plans/{plan_id}/critique")
async def critique_plan(plan_id: str, critique_req: PlanCritiqueRequest, request: Request):
    """Submit a critique for a plan and generate a revised plan."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Import planner modules
        from lightning_core.planner.planner import replan_with_critique
        
        # Use the global plan store
        global plan_store
        if not plan_store:
            from lightning_core.planner.storage import PlanStore
            plan_store = PlanStore()
        
        # Get the original plan
        original_plan = None
        if hasattr(plan_store, 'mem'):
            plan_record = plan_store.mem.get(plan_id)
            if plan_record and plan_record.get('pk') == user_id:
                original_plan = plan_record.get('plan', {})
                original_plan['id'] = plan_id
        
        if not original_plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Get the original instruction
        instruction_id = critique_req.instruction_id or original_plan.get('instruction_id')
        if not instruction_id:
            raise HTTPException(status_code=400, detail="Instruction ID required for replanning")
        
        # Get the instruction details
        instruction = instructions_storage.get(instruction_id)
        if not instruction or instruction.get('user_id') != user_id:
            raise HTTPException(status_code=404, detail="Instruction not found")
        
        # Build the original instruction text
        from lightning_core.vextir_os.instruction_processor import InstructionProcessor
        processor = InstructionProcessor(runtime)
        original_instruction_text = processor._build_plan_instruction(instruction)
        
        # Generate revised plan
        logger.info(f"Generating revised plan based on critique: {critique_req.critique}")
        revised_plan = await replan_with_critique(
            original_plan=original_plan,
            user_critique=critique_req.critique,
            original_instruction=original_instruction_text,
            user_id=user_id
        )
        
        # Store the revised plan
        revised_plan_id = plan_store.save(user_id, revised_plan)
        
        logger.info(f"Generated and stored revised plan {revised_plan_id}")
        
        return {
            "success": True,
            "revised_plan_id": revised_plan_id,
            "original_plan_id": plan_id,
            "message": "Revised plan created successfully",
            "plan": {
                **revised_plan,
                "id": revised_plan_id,
                "status": "revised",
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to critique plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Task endpoints
@app.post("/api/tasks")
async def create_task(task_req: TaskRequest, request: Request):
    """Create a new task."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")

        # Create task event
        event = EventMessage(
            event_type="task.create",
            data={
                "title": task_req.title,
                "description": task_req.description,
                "assignedTo": task_req.assignedTo or user_id,
                "dueDate": task_req.dueDate,
                "priority": task_req.priority,
                "status": "pending",
            },
            metadata={"userID": user_id, "source": "api"},
        )

        # Publish event
        await runtime.publish_event(event)

        # Return task (in production, this would query the database)
        return {
            "success": True,
            "task": {
                "id": f"task-{datetime.utcnow().timestamp()}",
                **task_req.dict(),
                "status": "pending",
                "createdAt": datetime.utcnow().isoformat(),
            },
        }

    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
async def get_tasks(request: Request):
    """Get tasks for the current user."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")

        # In production, this would query the database
        # For now, return mock data
        return {
            "tasks": [
                {
                    "id": "task-1",
                    "title": "Sample Task",
                    "description": "This is a sample task",
                    "assignedTo": user_id,
                    "status": "pending",
                    "priority": "medium",
                    "createdAt": datetime.utcnow().isoformat(),
                }
            ],
            "total": 1,
        }

    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notifications")
async def get_notifications(request: Request):
    """Get notifications for the current user."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")

        # In production, this would be derived from actual task/event data
        # For now, return mock notifications based on recent tasks
        return {
            "notifications": [
                {
                    "id": "notif-1",
                    "type": "task_created",
                    "title": "New Task Assigned",
                    "message": "Sample Task has been assigned to you",
                    "timestamp": datetime.utcnow().isoformat(),
                    "read": False,
                    "priority": "medium"
                },
                {
                    "id": "notif-2", 
                    "type": "system",
                    "title": "Welcome to Lightning",
                    "message": "Your context hub is ready to use",
                    "timestamp": datetime.utcnow().isoformat(),
                    "read": True,
                    "priority": "low"
                }
            ],
            "unread_count": 1,
            "total": 2
        }

    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Driver endpoints
@app.get("/api/drivers")
async def get_drivers():
    """Get registered drivers."""
    try:
        from lightning_core.vextir_os.registries import get_driver_registry

        registry = get_driver_registry()
        drivers = []

        for driver_id in registry._drivers:
            driver = await registry.get_driver(driver_id)
            manifest = registry._manifests.get(driver_id)
            if manifest:
                drivers.append(
                    {
                        "id": driver_id,
                        "name": manifest.name,
                        "description": manifest.description,
                        "version": manifest.version,
                        "type": manifest.driver_type,
                    }
                )

        return {"drivers": drivers, "total": len(drivers)}

    except Exception as e:
        logger.error(f"Failed to get drivers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Tool endpoints
@app.get("/api/tools")
async def get_tools():
    """Get available tools."""
    try:
        from lightning_core.vextir_os.registries import get_tool_registry

        registry = get_tool_registry()
        tools = []

        for tool_id, tool_def in registry._tools.items():
            tools.append(
                {
                    "id": tool_id,
                    "name": tool_def.get("name", tool_id),
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {}),
                }
            )

        return {"tools": tools, "total": len(tools)}

    except Exception as e:
        logger.error(f"Failed to get tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Model endpoints
@app.get("/api/models")
async def get_models():
    """Get available AI models."""
    try:
        from lightning_core.vextir_os.registries import get_model_registry

        registry = get_model_registry()
        models = []

        for model_id, model_def in registry._models.items():
            models.append(
                {
                    "id": model_id,
                    "provider": model_def.get("provider", ""),
                    "name": model_def.get("name", model_id),
                    "description": model_def.get("description", ""),
                    "capabilities": model_def.get("capabilities", []),
                }
            )

        return {"models": models, "total": len(models)}

    except Exception as e:
        logger.error(f"Failed to get models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Chat API endpoints
@app.get("/api/chats")
async def get_chat_threads(request: Request, limit: int = 50):
    """Get list of chat threads for the current user."""
    try:
        user_id = request.headers.get("X-User-ID", "local-user")
        chats = await chat_persistence.list_chats(user_id, limit)
        return {"chats": chats, "total": len(chats)}
    except Exception as e:
        logger.error(f"Failed to get chat threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chats/{chat_id}")
async def get_chat_thread(chat_id: str, request: Request):
    """Get a specific chat thread."""
    try:
        user_id = request.headers.get("X-User-ID", "local-user")
        thread = await chat_persistence.load_chat(chat_id, user_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Chat thread not found")
        return thread.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time chat
@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time chat communication."""
    connection_id = str(uuid.uuid4())
    await manager.connect(websocket, connection_id, user_id)
    
    # Initialize or load chat thread
    thread = None
    thread_id = None
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket message: {data}")
            
            if data.get("type") == "init_chat":
                # Initialize chat - either load existing or create new
                thread_id = data.get("thread_id")
                if thread_id and thread_id not in ["new", "latest"]:
                    # Load existing thread
                    thread = await chat_persistence.load_chat(thread_id, user_id)
                    if thread:
                        logger.info(f"Loaded existing chat thread {thread_id}")
                        # Send thread history to client
                        await websocket.send_json({
                            "type": "chat_loaded",
                            "thread_id": thread_id,
                            "messages": [msg.dict() for msg in thread.messages],
                            "title": thread.title
                        })
                else:
                    # Create new thread or load latest
                    if thread_id == "latest":
                        thread = await chat_persistence.get_latest_chat(user_id)
                        if thread:
                            logger.info(f"Loaded latest chat thread {thread.id}")
                            await websocket.send_json({
                                "type": "chat_loaded",
                                "thread_id": thread.id,
                                "messages": [msg.dict() for msg in thread.messages],
                                "title": thread.title
                            })
                    
                    if not thread:
                        # Create new thread
                        thread = ChatThread(
                            user_id=user_id,
                            session_id=data.get("session_id", connection_id)
                        )
                        logger.info(f"Created new chat thread {thread.id}")
                        await websocket.send_json({
                            "type": "chat_created",
                            "thread_id": thread.id
                        })
                
                manager.active_threads[connection_id] = thread
            
            elif data.get("type") == "chat_message":
                # Ensure we have a thread
                if connection_id not in manager.active_threads:
                    thread = ChatThread(
                        user_id=user_id,
                        session_id=data.get("session_id", connection_id)
                    )
                    manager.active_threads[connection_id] = thread
                else:
                    thread = manager.active_threads[connection_id]
                
                # Generate a unique request ID
                request_id = str(uuid.uuid4())
                manager.pending_responses[request_id] = connection_id
                
                # Add user message to thread
                user_message = data.get("message", "")
                thread.messages.append(ChatMessage(
                    role="user",
                    content=user_message,
                    metadata={"request_id": request_id}
                ))
                thread.updated_at = datetime.utcnow().isoformat()
                
                # Save thread after user message
                try:
                    doc_id = await chat_persistence.save_chat(thread)
                    logger.info(f"Saved chat thread {thread.id} to document {doc_id}")
                except Exception as e:
                    logger.error(f"Failed to save chat thread: {e}")
                
                # Use full conversation history if provided, otherwise just current message
                messages = data.get("messages", [])
                if not messages:
                    # Use thread messages for context
                    messages = [{"role": msg.role, "content": msg.content} 
                               for msg in thread.messages]
                
                # Create chat event
                event = EventMessage(
                    event_type="llm.chat",
                    data={
                        "messages": messages,
                        "model": data.get("model", "gpt-4"),
                        "temperature": data.get("temperature", 0.7)
                    },
                    metadata={
                        "userID": user_id,
                        "source": "websocket_chat",
                        "request_id": request_id,
                        "session_id": data.get("session_id", connection_id),
                        "thread_id": thread.id
                    }
                )
                
                # Publish event to event bus
                logger.info(f"[TRACE] Publishing event {event.event_type} with request_id {request_id}, event_id={event.id}")
                await runtime.publish_event(event)
                logger.info(f"[TRACE] Event published successfully: event_id={event.id}")
                
                # Send acknowledgment
                await websocket.send_json({
                    "type": "ack",
                    "request_id": request_id,
                    "message": "Message received and processing"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        if connection_id in manager.active_threads:
            del manager.active_threads[connection_id]
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(connection_id)
        if connection_id in manager.active_threads:
            del manager.active_threads[connection_id]


# Instruction endpoints
instructions_storage = {}  # In-memory storage for now
plan_errors_storage = {}  # Storage for plan generation errors

# Add some test instructions
test_instructions = [
    {
        "id": "test-1",
        "name": "Plan Summary Test",
        "description": "Test instruction to verify plan summary generation",
        "enabled": False,
        "trigger": {
            "event_type": "manual",
            "providers": [],
            "conditions": {}
        },
        "action": {
            "type": "conseil_task",
            "config": {
                "task_description": "Generate a plan summary"
            }
        },
        "execution_count": 0,
        "last_executed_at": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "user_id": "demo-user"
    },
    {
        "id": "test-2",
        "name": "UI Test Workflow",
        "description": "When someone mentions a bug in Slack, create a GitHub issue",
        "enabled": True,
        "trigger": {
            "event_type": "slack.message",
            "providers": ["slack"],
            "conditions": {
                "contains": ["bug", "issue", "problem"]
            }
        },
        "action": {
            "type": "github_issue",
            "config": {
                "repository": "myorg/myrepo",
                "title": "Bug reported in Slack",
                "labels": ["bug", "from-slack"]
            }
        },
        "execution_count": 0,
        "last_executed_at": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "user_id": "demo-user"
    }
]

# Initialize with test data
for instr in test_instructions:
    instructions_storage[instr["id"]] = instr

@app.get("/api/instructions", response_model=List[InstructionResponse])
async def list_instructions(request: Request):
    """Get list of user instructions."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Filter instructions by user
        user_instructions = [
            instr for instr in instructions_storage.values()
            if instr.get("user_id") == user_id
        ]
        
        return user_instructions
        
    except Exception as e:
        logger.error(f"Failed to list instructions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/instructions", response_model=InstructionResponse, status_code=201)
async def create_instruction(instruction_req: InstructionRequest, request: Request):
    """Create a new instruction."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Generate instruction ID
        instruction_id = str(uuid.uuid4())
        current_time = datetime.utcnow().isoformat()
        
        # Create instruction record
        instruction = {
            "id": instruction_id,
            "name": instruction_req.name,
            "description": instruction_req.description,
            "enabled": instruction_req.enabled,
            "trigger": instruction_req.trigger.dict(),
            "action": instruction_req.action.dict(),
            "execution_count": 0,
            "last_executed_at": None,
            "created_at": current_time,
            "updated_at": current_time,
            "user_id": user_id,
        }
        
        # Store instruction
        instructions_storage[instruction_id] = instruction
        
        # Initialize plan errors dict if needed (at module level)
        global plan_errors_storage
        if 'plan_errors_storage' not in globals():
            plan_errors_storage = {}
        plan_errors_storage[instruction_id] = None
        
        # Publish instruction.created event
        if runtime:
            try:
                event = EventMessage(
                    event_type="instruction.created",
                    data={
                        "instruction_id": instruction_id,
                        "instruction": instruction,
                    },
                    metadata={
                        "userID": user_id,
                        "source": "api",
                        "instruction_id": instruction_id,
                    },
                )
                await runtime.publish_event(event)
            except Exception as e:
                logger.warning(f"Failed to publish instruction.created event: {e}")
        
        return instruction
        
    except Exception as e:
        logger.error(f"Failed to create instruction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/instructions/{instruction_id}", response_model=InstructionResponse)
async def update_instruction(instruction_id: str, instruction_req: InstructionRequest, request: Request):
    """Update an existing instruction."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Check if instruction exists and belongs to user
        if instruction_id not in instructions_storage:
            raise HTTPException(status_code=404, detail="Instruction not found")
            
        existing = instructions_storage[instruction_id]
        if existing.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update instruction
        instruction = {
            **existing,
            "name": instruction_req.name,
            "description": instruction_req.description,
            "enabled": instruction_req.enabled,
            "trigger": instruction_req.trigger.dict(),
            "action": instruction_req.action.dict(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        instructions_storage[instruction_id] = instruction
        
        # Publish instruction.updated event
        if runtime:
            try:
                event = EventMessage(
                    event_type="instruction.updated",
                    data={
                        "instruction_id": instruction_id,
                        "instruction": instruction,
                        "previous": existing,
                    },
                    metadata={
                        "userID": user_id,
                        "source": "api",
                        "instruction_id": instruction_id,
                    },
                )
                await runtime.publish_event(event)
            except Exception as e:
                logger.warning(f"Failed to publish instruction.updated event: {e}")
        
        return instruction
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update instruction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/instructions/{instruction_id}")
async def delete_instruction(instruction_id: str, request: Request):
    """Delete an instruction."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Check if instruction exists and belongs to user
        if instruction_id not in instructions_storage:
            raise HTTPException(status_code=404, detail="Instruction not found")
            
        existing = instructions_storage[instruction_id]
        if existing.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete instruction
        del instructions_storage[instruction_id]
        
        # Publish instruction.deleted event
        if runtime:
            try:
                event = EventMessage(
                    event_type="instruction.deleted",
                    data={
                        "instruction_id": instruction_id,
                        "instruction": existing,
                    },
                    metadata={
                        "userID": user_id,
                        "source": "api",
                        "instruction_id": instruction_id,
                    },
                )
                await runtime.publish_event(event)
            except Exception as e:
                logger.warning(f"Failed to publish instruction.deleted event: {e}")
        
        return {"message": "Instruction deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete instruction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Temporary endpoint to set plan errors for testing
@app.post("/api/instructions/{instruction_id}/set-plan-error")
async def set_plan_error(instruction_id: str, error_data: dict):
    """Temporary endpoint to set plan generation errors for testing."""
    plan_errors_storage[instruction_id] = error_data.get("error", "Plan generation failed")
    return {"status": "error set"}


@app.patch("/api/instructions/{instruction_id}/toggle")
async def toggle_instruction(instruction_id: str, request: Request):
    """Toggle instruction enabled status."""
    try:
        # Get user ID from header or use default
        user_id = request.headers.get("X-User-ID", "local-user")
        
        # Check if instruction exists and belongs to user
        if instruction_id not in instructions_storage:
            raise HTTPException(status_code=404, detail="Instruction not found")
            
        existing = instructions_storage[instruction_id]
        if existing.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Toggle enabled status
        instruction = {
            **existing,
            "enabled": not existing["enabled"],
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        instructions_storage[instruction_id] = instruction
        
        # Publish instruction.toggled event
        if runtime:
            try:
                event = EventMessage(
                    event_type="instruction.toggled",
                    data={
                        "instruction_id": instruction_id,
                        "instruction": instruction,
                        "previous_enabled": existing["enabled"],
                        "current_enabled": instruction["enabled"],
                    },
                    metadata={
                        "userID": user_id,
                        "source": "api",
                        "instruction_id": instruction_id,
                    },
                )
                await runtime.publish_event(event)
            except Exception as e:
                logger.warning(f"Failed to publish instruction.toggled event: {e}")
        
        return instruction
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle instruction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Lightning Core API",
        "version": "1.0.0",
        "mode": os.getenv("LIGHTNING_MODE", "local"),
        "endpoints": {
            "health": "/health",
            "events": "/api/events",
            "plans": "/api/plans",
            "tasks": "/api/tasks",
            "instructions": "/api/instructions",
            "drivers": "/api/drivers",
            "tools": "/api/tools",
            "models": "/api/models",
        },
    }


if __name__ == "__main__":
    uvicorn.run("lightning_core.api.main:app", host="0.0.0.0", port=8000, reload=True)
