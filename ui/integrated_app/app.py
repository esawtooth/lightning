from fastapi import FastAPI, HTTPException, Depends, Header, Cookie, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
import os
import requests
import logging
from common.jwt_utils import verify_token
from typing import Optional

# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:7071/api")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
AUTH_GATEWAY_URL = os.environ.get("AUTH_GATEWAY_URL")
CHAINLIT_URL = os.environ.get("CHAINLIT_URL")

app = FastAPI(title="Vextir Integrated Dashboard")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Setup templates and static files
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


def _get_token(
    token: str | None = None,
    authorization: str | None = Header(None, alias="Authorization"),
    auth_cookie: str | None = Cookie(None, alias="auth_token"),
):
    """Return bearer token from query param, header, cookie or env."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    if auth_cookie:
        return auth_cookie
    return token or AUTH_TOKEN


def verify_user_token(token: str) -> Optional[str]:
    """Verify JWT token and return username."""
    try:
        return verify_token(token)
    except Exception as e:
        logging.warning(f"Invalid token: {e}")
        return None


async def authenticate_user(request: Request) -> Optional[str]:
    """Authenticate user from session or token."""
    token = request.cookies.get("auth_token")
    if token:
        username = verify_user_token(token)
        if username:
            return username
    return None


def _resolve_gateway_url(request: Request) -> str:
    """Return the URL of the authentication gateway for the request."""
    base = AUTH_GATEWAY_URL.rstrip("/") if AUTH_GATEWAY_URL else None
    if base:
        return base
    
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.hostname or "localhost")
    host = host.split(":")[0]
    return f"{scheme}://{host}"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Authentication middleware for all routes."""
    # Allow health checks and static assets
    if request.url.path in ["/health"] or request.url.path.startswith("/static"):
        return await call_next(request)

    # Check authentication
    username = await authenticate_user(request)
    if not username:
        # For development, allow access without authentication if AUTH_GATEWAY_URL is not set
        if not AUTH_GATEWAY_URL:
            request.state.username = "demo-user"
            response = await call_next(request)
            return response
        
        # Redirect to auth gateway
        gateway_base = _resolve_gateway_url(request)
        redirect_url = f"{gateway_base}/?redirect={request.url}"
        return RedirectResponse(url=redirect_url)

    # Store username in request state
    request.state.username = username
    response = await call_next(request)
    return response


def _api_headers(token: str | None) -> dict:
    """Generate API headers with authorization."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return headers


# Main dashboard route
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page with integrated navigation."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": username,
        "active_page": "dashboard"
    })


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Tasks management page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "username": username,
        "active_page": "tasks"
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "username": username,
        "active_page": "chat"
    })


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    """Notifications page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "username": username,
        "active_page": "notifications"
    })


# API endpoints
@app.get("/api/tasks")
async def list_tasks(token: str = Depends(_get_token)):
    """Get list of tasks."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/tasks/{task_id}")
async def task_detail(task_id: str, token: str = Depends(_get_token)):
    """Get task details."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks/{task_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/analytics")
async def analytics(token: str = Depends(_get_token)):
    """Return basic analytics derived from tasks."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    tasks = resp.json()
    total = len(tasks)
    status_counts: dict[str, int] = {}
    total_cost = 0.0
    
    for t in tasks:
        status = t.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        cost = t.get("cost", {}).get("cost")
        if cost is not None:
            try:
                total_cost += float(cost)
            except Exception:
                pass
    
    return {"total": total, "status": status_counts, "cost": total_cost}


@app.get("/api/notifications")
async def notifications(token: str = Depends(_get_token)):
    """Return recent task notifications."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    tasks = resp.json()
    tasks.sort(key=lambda t: t.get("updated_at", t.get("created_at", "")), reverse=True)
    notifs = [
        {
            "id": t.get("id"),
            "status": t.get("status"),
            "updated_at": t.get("updated_at"),
        }
        for t in tasks[:20]
    ]
    return {"notifications": notifs}


class EventIn(BaseModel):
    type: str
    metadata: dict


@app.post("/api/events")
async def create_event(event: EventIn, token: str = Depends(_get_token)):
    """Create a new event."""
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "dashboard",
        "type": event.type,
        "metadata": event.metadata,
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{API_BASE}/events", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "queued"}


# Context Hub endpoints
@app.get("/context", response_class=HTMLResponse)
async def context_page(request: Request):
    """Context hub management page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("context.html", {
        "request": request,
        "username": username,
        "active_page": "context"
    })


@app.get("/instructions", response_class=HTMLResponse)
async def instructions_page(request: Request):
    """Instructions management page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("instructions.html", {
        "request": request,
        "username": username,
        "active_page": "instructions"
    })


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Events monitoring page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("events.html", {
        "request": request,
        "username": username,
        "active_page": "events"
    })


@app.get("/providers", response_class=HTMLResponse)
async def providers_page(request: Request):
    """Provider configuration page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("providers.html", {
        "request": request,
        "username": username,
        "active_page": "providers"
    })


@app.get("/api/context/status")
async def context_status(token: str = Depends(_get_token)):
    """Get user's context hub status."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/status", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/context/initialize")
async def initialize_context(token: str = Depends(_get_token)):
    """Initialize user's context hub."""
    headers = _api_headers(token)
    resp = requests.post(f"{API_BASE}/context/initialize", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/context/folders")
async def get_folders(token: str = Depends(_get_token)):
    """Get user's folder structure."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/folders", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/context/search")
async def search_context(q: str, limit: int = 10, token: str = Depends(_get_token)):
    """Search user's context hub."""
    headers = _api_headers(token)
    params = {"q": q, "limit": limit}
    resp = requests.get(f"{API_BASE}/context/search", headers=headers, params=params)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class DocumentIn(BaseModel):
    name: str
    content: str
    folder_id: Optional[str] = None


@app.post("/api/context/documents")
async def create_document(doc: DocumentIn, token: str = Depends(_get_token)):
    """Create a new document in user's context hub."""
    headers = _api_headers(token)
    payload = {
        "name": doc.name,
        "content": doc.content,
        "folder_id": doc.folder_id
    }
    resp = requests.post(f"{API_BASE}/context/documents", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Instructions API endpoints
@app.get("/api/instructions")
async def list_instructions(token: str = Depends(_get_token)):
    """Get list of user instructions."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/instructions", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class InstructionIn(BaseModel):
    name: str
    description: str
    trigger: dict
    action: dict
    enabled: bool = True


@app.post("/api/instructions")
async def create_instruction(instruction: InstructionIn, token: str = Depends(_get_token)):
    """Create a new instruction."""
    headers = _api_headers(token)
    payload = instruction.dict()
    resp = requests.post(f"{API_BASE}/instructions", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.put("/api/instructions/{instruction_id}")
async def update_instruction(instruction_id: str, instruction: InstructionIn, token: str = Depends(_get_token)):
    """Update an existing instruction."""
    headers = _api_headers(token)
    payload = instruction.dict()
    resp = requests.put(f"{API_BASE}/instructions/{instruction_id}", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.delete("/api/instructions/{instruction_id}")
async def delete_instruction(instruction_id: str, token: str = Depends(_get_token)):
    """Delete an instruction."""
    headers = _api_headers(token)
    resp = requests.delete(f"{API_BASE}/instructions/{instruction_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "deleted"}


@app.patch("/api/instructions/{instruction_id}/toggle")
async def toggle_instruction(instruction_id: str, token: str = Depends(_get_token)):
    """Toggle instruction enabled/disabled status."""
    headers = _api_headers(token)
    resp = requests.patch(f"{API_BASE}/instructions/{instruction_id}/toggle", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Events API endpoints
@app.get("/api/events/stream")
async def get_events(limit: int = 50, event_type: str = None, provider: str = None, token: str = Depends(_get_token)):
    """Get recent events with optional filtering."""
    headers = _api_headers(token)
    params = {"limit": limit}
    if event_type:
        params["event_type"] = event_type
    if provider:
        params["provider"] = provider
    
    resp = requests.get(f"{API_BASE}/events", headers=headers, params=params)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class TestEventIn(BaseModel):
    event_type: str
    provider: str
    test_data: dict


@app.post("/api/events/test")
async def create_test_event(test_event: TestEventIn, token: str = Depends(_get_token)):
    """Create a test event for instruction testing."""
    headers = _api_headers(token)
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "UI-Test",
        "type": test_event.event_type,
        "metadata": {
            "operation": "test",
            "provider": test_event.provider,
            **test_event.test_data
        }
    }
    resp = requests.post(f"{API_BASE}/events", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "test_event_created"}


# Providers API endpoints
@app.get("/api/providers/status")
async def get_provider_status(token: str = Depends(_get_token)):
    """Get status of all configured providers."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/connector/status", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/providers/{provider}/auth")
async def start_provider_auth(provider: str, token: str = Depends(_get_token)):
    """Start OAuth flow for a provider."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/connector/auth/{provider}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/providers/{provider}/test")
async def test_provider_connection(provider: str, token: str = Depends(_get_token)):
    """Test connection to a provider."""
    headers = _api_headers(token)
    resp = requests.post(f"{API_BASE}/connector/test/{provider}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.delete("/api/providers/{provider}")
async def disconnect_provider(provider: str, token: str = Depends(_get_token)):
    """Disconnect a provider."""
    headers = _api_headers(token)
    resp = requests.delete(f"{API_BASE}/connector/{provider}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "disconnected"}


# Context summaries API endpoints
@app.get("/api/summaries")
async def get_summaries(token: str = Depends(_get_token)):
    """Get all context summaries."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/summaries", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/summaries/{summary_key}")
async def get_summary(summary_key: str, token: str = Depends(_get_token)):
    """Get a specific context summary."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/summaries/{summary_key}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/summaries/{summary_key}/synthesize")
async def trigger_synthesis(summary_key: str, token: str = Depends(_get_token)):
    """Manually trigger synthesis for a context summary."""
    headers = _api_headers(token)
    resp = requests.post(f"{API_BASE}/context/summaries/{summary_key}/synthesize", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "vextir-integrated-dashboard",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
