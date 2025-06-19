"""
Health check endpoints for Lightning Unified UI.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import settings

router = APIRouter()


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str
    environment: str
    services: Dict[str, str]
    features: Dict[str, bool]


@router.get("/", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Basic health check endpoint.
    
    Returns application status and configuration.
    """
    # TODO: Check actual service connections
    services = {
        "api": "healthy",
        "database": "healthy",
        "redis": "healthy",
        "websocket": "healthy",
    }
    
    features = {
        "chat": settings.enable_chat,
        "tasks": settings.enable_tasks,
        "monitoring": settings.enable_monitoring,
        "notifications": settings.enable_notifications,
    }
    
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=settings.app_version,
        environment=settings.app_env,
        services=services,
        features=features,
    )


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes liveness probe endpoint.
    
    Returns 200 if the application is running.
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.
    
    Returns 200 if the application is ready to serve requests.
    """
    # TODO: Check if all required services are connected
    ready = True
    checks = {
        "database": True,
        "redis": True,
        "api_backend": True,
    }
    
    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }