"""API routers for Lightning Unified UI."""

from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .chat import router as chat_router
from .tasks import router as tasks_router
from .events import router as events_router
from .health import router as health_router
from .websocket import router as websocket_router

__all__ = [
    "auth_router",
    "dashboard_router", 
    "chat_router",
    "tasks_router",
    "events_router",
    "health_router",
    "websocket_router",
]