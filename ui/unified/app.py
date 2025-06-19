"""
Lightning Unified UI - Main Application.

This is the consolidated UI that combines chat, dashboard, and task management
into a single cohesive interface.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import settings, get_settings
from auth.middleware import AuthenticationMiddleware
from api import (
    auth_router,
    dashboard_router,
    chat_router,
    tasks_router,
    events_router,
    health_router,
    websocket_router,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' if settings.log_format == "text" else None
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.app_env}")
    
    # Initialize services
    try:
        # TODO: Initialize Redis connection
        # TODO: Initialize event bus connection
        # TODO: Initialize storage connection
        # TODO: Start background tasks
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    # TODO: Close connections
    # TODO: Cancel background tasks
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url="/api/redoc" if settings.app_env != "production" else None,
)

# Configure middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="lightning_session",
    max_age=3600 * 24 * 7,  # 1 week
    same_site="lax",
    https_only=settings.app_env == "production",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.app_env == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["lightning.ai", "*.lightning.ai"],
    )

# Add authentication middleware
app.add_middleware(AuthenticationMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Include API routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(events_router, prefix="/api/events", tags=["events"])
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(websocket_router, tags=["websocket"])


# Root route - Dashboard
@app.get("/")
async def root(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": getattr(request.state, "user", None),
            "settings": {
                "app_name": settings.app_name,
                "enable_chat": settings.enable_chat,
                "enable_tasks": settings.enable_tasks,
                "enable_notifications": settings.enable_notifications,
            }
        }
    )


# Chat page
@app.get("/chat")
async def chat_page(request: Request):
    """Chat interface page."""
    if not settings.enable_chat:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Chat feature is disabled"}
        )
    
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user": getattr(request.state, "user", None),
            "ws_url": f"ws://{request.url.hostname}:{request.url.port}/ws",
        }
    )


# Tasks page
@app.get("/tasks")
async def tasks_page(request: Request):
    """Task management page."""
    if not settings.enable_tasks:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Tasks feature is disabled"}
        )
    
    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "user": getattr(request.state, "user", None),
        }
    )


# Notifications page
@app.get("/notifications")
async def notifications_page(request: Request):
    """Notifications page."""
    if not settings.enable_notifications:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Notifications feature is disabled"}
        )
    
    return templates.TemplateResponse(
        "notifications.html",
        {
            "request": request,
            "user": getattr(request.state, "user", None),
        }
    )


# Settings page
@app.get("/settings")
async def settings_page(request: Request):
    """User settings page."""
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": getattr(request.state, "user", None),
        }
    )


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors."""
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Page not found", "status_code": 404},
        status_code=404
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {exc}")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Internal server error", "status_code": 500},
        status_code=500
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )