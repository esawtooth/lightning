"""
Lightning Core API - Main FastAPI application

This provides REST API endpoints for the Lightning Core system,
replacing Azure Functions endpoints for local development.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from lightning_core.runtime import get_runtime, initialize_runtime
from lightning_core.abstractions import (
    RuntimeConfig, ExecutionMode, EventMessage, Document
)
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_all_drivers
)


# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


# Global runtime instance
runtime = None


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
    plan_type: str = Field(default="acyclic", description="Plan type: acyclic or reactive")


class TaskRequest(BaseModel):
    """Task creation request."""
    title: str
    description: Optional[str] = None
    assignedTo: Optional[str] = None
    dueDate: Optional[str] = None
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global runtime
    
    logger.info("Starting Lightning Core API...")
    
    # Configure environment
    configure_drivers_for_environment()
    
    # Initialize runtime
    config = RuntimeConfig.from_env()
    runtime = await initialize_runtime(config)
    
    # Initialize drivers
    await initialize_all_drivers()
    
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
    lifespan=lifespan
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services = {
        "api": "healthy",
        "storage": "unknown",
        "event_bus": "unknown",
        "context_hub": "unknown"
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
    
    overall_status = "healthy" if all(s == "healthy" or s == "unknown" for s in services.values()) else "degraded"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        services=services
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
                "submitted_via": "api"
            }
        )
        
        # Publish event
        await runtime.publish_event(event)
        
        return EventResponse(
            success=True,
            event_id=event.id,
            message=f"Event {event.event_type} submitted successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to submit event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/types")
async def get_event_types():
    """Get supported event types."""
    # This would come from driver registry in full implementation
    return {
        "event_types": [
            "user.login",
            "user.logout",
            "user.action",
            "task.create",
            "task.update",
            "task.complete",
            "plan.create",
            "plan.execute",
            "system.health_check",
            "agent.invoke",
            "tool.execute"
        ]
    }


# Plan endpoints
@app.post("/api/plans")
async def create_plan(plan_req: PlanRequest):
    """Create a new plan from natural language description."""
    try:
        # This would use the planner module
        # For now, return a mock response
        return {
            "success": True,
            "plan_id": f"plan-{datetime.utcnow().timestamp()}",
            "message": "Plan creation not yet implemented in local mode",
            "plan": {
                "description": plan_req.description,
                "type": plan_req.plan_type,
                "status": "draft"
            }
        }
    except Exception as e:
        logger.error(f"Failed to create plan: {e}")
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
                "status": "pending"
            },
            metadata={
                "userID": user_id,
                "source": "api"
            }
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
                "createdAt": datetime.utcnow().isoformat()
            }
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
                    "createdAt": datetime.utcnow().isoformat()
                }
            ],
            "total": 1
        }
        
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
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
                drivers.append({
                    "id": driver_id,
                    "name": manifest.name,
                    "description": manifest.description,
                    "version": manifest.version,
                    "type": manifest.driver_type
                })
        
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
            tools.append({
                "id": tool_id,
                "name": tool_def.get("name", tool_id),
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("parameters", {})
            })
        
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
            models.append({
                "id": model_id,
                "provider": model_def.get("provider", ""),
                "name": model_def.get("name", model_id),
                "description": model_def.get("description", ""),
                "capabilities": model_def.get("capabilities", [])
            })
        
        return {"models": models, "total": len(models)}
        
    except Exception as e:
        logger.error(f"Failed to get models: {e}")
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
            "drivers": "/api/drivers",
            "tools": "/api/tools",
            "models": "/api/models"
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "lightning_core.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )