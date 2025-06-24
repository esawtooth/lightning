from fastapi import FastAPI, HTTPException, Depends, Header, Cookie, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timedelta
from starlette.middleware.sessions import SessionMiddleware
import os
import requests
import logging
from common.jwt_utils import verify_token
from typing import Optional
import httpx
from urllib.parse import urlencode

# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api")
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
        claims = verify_token(token)
        # Extract user ID from claims
        user_id = claims.get("oid") or claims.get("sub")
        if not user_id:
            logging.warning("No user ID in token claims")
            return None
        # Get username from claims
        username = claims.get("preferred_username") or claims.get("email") or user_id
        return username
    except Exception as e:
        logging.warning(f"Invalid token: {e}")
        return None


async def authenticate_user(request: Request) -> Optional[str]:
    """Authenticate user from session or token."""
    # Get tokens from cookies
    auth_token = request.cookies.get("auth_token")
    refresh_token = request.cookies.get("refresh_token")
    
    if not auth_token and not refresh_token:
        return None
    
    # Try auth token first
    if auth_token:
        username = verify_user_token(auth_token)
        if username:
            return username
    
    # Try refresh token if auth token failed
    if refresh_token:
        new_tokens = await refresh_access_token(refresh_token)
        if new_tokens and new_tokens.get("id_token"):
            # Store new tokens for middleware to set as cookies
            request.state._new_auth_token = new_tokens.get("id_token")
            request.state._new_refresh_token = new_tokens.get("refresh_token")
            
            # Verify and return username from new token
            username = verify_user_token(new_tokens["id_token"])
            if username:
                return username
    
    return None


async def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh the access token using the refresh token."""
    client_id = os.environ.get("AAD_CLIENT_ID")
    client_secret = os.environ.get("AAD_CLIENT_SECRET")
    tenant_id = os.environ.get("AAD_TENANT_ID")
    
    if not all([client_id, client_secret, tenant_id]):
        return None
    
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "openid profile email User.Read offline_access"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Token refresh failed: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Error refreshing token: {e}")
            return None


def _resolve_gateway_url(request: Request) -> str:
    """Return the URL of the authentication gateway for the request."""
    base = AUTH_GATEWAY_URL.rstrip("/") if AUTH_GATEWAY_URL else None
    if base:
        return base
    
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.hostname or "localhost")
    host = host.split(":")[0]
    # Default to /auth path when AUTH_GATEWAY_URL is not set
    return f"{scheme}://{host}/auth"


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
    
    # Set new tokens if they were refreshed
    if hasattr(request.state, '_new_auth_token') and request.state._new_auth_token:
        response.set_cookie(
            key="auth_token",
            value=request.state._new_auth_token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=3600  # 1 hour
        )
    
    if hasattr(request.state, '_new_refresh_token') and request.state._new_refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=request.state._new_refresh_token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=86400 * 30  # 30 days
        )
    
    return response


def _api_headers(token: str | None, username: str | None = None) -> dict:
    """Generate API headers with authorization."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    # Add user ID header for user-specific resources
    if username:
        headers["X-User-ID"] = username
    
    return headers


# Landing page route (main entry point)
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with workflow cards."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "username": username,
        "active_page": "home"
    })

# Dashboard route
@app.get("/dashboard", response_class=HTMLResponse)
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


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = None, state: str = None):
    """Handle OAuth callback from Azure AD."""
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    
    # Get configuration
    client_id = os.environ.get("AAD_CLIENT_ID")
    client_secret = os.environ.get("AAD_CLIENT_SECRET")
    tenant_id = os.environ.get("AAD_TENANT_ID")
    
    if not all([client_id, client_secret, tenant_id]):
        raise HTTPException(status_code=500, detail="Azure AD configuration missing")
    
    # Build callback URL
    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("host", "localhost")
    callback_url = f"{scheme}://{host}/auth/callback"
    
    # Exchange code for tokens
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                    "scope": "openid profile email User.Read offline_access"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail="Token exchange failed")
            
            token_data = response.json()
            
            # Verify the ID token
            id_token = token_data.get("id_token")
            if not id_token:
                raise HTTPException(status_code=400, detail="No ID token received")
            
            # Verify token to ensure it's valid
            try:
                claims = verify_token(id_token)
            except Exception as e:
                logger.error(f"Token verification failed: {e}")
                raise HTTPException(status_code=400, detail="Invalid token")
            
            # Create response with redirect
            redirect_url = state or "/"
            response = RedirectResponse(url=redirect_url)
            
            # Set auth cookies
            response.set_cookie(
                key="auth_token",
                value=id_token,
                httponly=True,
                secure=scheme == "https",
                samesite="lax",
                max_age=3600  # 1 hour
            )
            
            # Store refresh token if available
            refresh_token = token_data.get("refresh_token")
            if refresh_token:
                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=scheme == "https",
                    samesite="lax",
                    max_age=86400 * 30  # 30 days
                )
            
            return response
            
        except httpx.RequestError as e:
            logger.error(f"Request error during token exchange: {e}")
            raise HTTPException(status_code=500, detail="Failed to contact Azure AD")


@app.get("/logout")
async def logout(request: Request):
    """Logout user by clearing cookies and redirecting to Azure AD logout."""
    tenant_id = os.environ.get("AAD_TENANT_ID")
    client_id = os.environ.get("AAD_CLIENT_ID")
    
    # Build post-logout redirect URL
    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("host", "localhost")
    post_logout_url = f"{scheme}://{host}/"
    
    # Build Azure AD logout URL
    logout_params = {
        "post_logout_redirect_uri": post_logout_url
    }
    
    if tenant_id:
        logout_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout?{urlencode(logout_params)}"
    else:
        # Fallback to just clearing cookies
        logout_url = "/"
    
    # Create redirect response
    response = RedirectResponse(url=logout_url)
    
    # Clear auth cookies
    response.delete_cookie(key="auth_token")
    response.delete_cookie(key="refresh_token")
    
    return response


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page."""
    username = getattr(request.state, "username", "User")
    
    # Get thread ID from query params
    thread_id = request.query_params.get("thread")
    
    # Determine the appropriate API base URL based on the request
    # Use the actual host from the request to support external access
    host_header = request.headers.get("host", "")
    if host_header:
        # Extract just the hostname/IP without port
        host = host_header.split(":")[0]
        # Use the same host but with API port 8000
        api_base = f"http://{host}:8000"
    else:
        # Fallback to localhost
        api_base = "http://localhost:8000"
    
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "username": username,
        "active_page": "chat",
        "api_base": api_base,
        "user_id": username,
        "chat_thread_id": thread_id
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
    
    result = resp.json()
    tasks = result.get("tasks", []) if isinstance(result, dict) else result
    
    # Sort by updated_at or created_at, handling missing fields
    def get_sort_key(task):
        return task.get("updated_at") or task.get("updatedAt") or task.get("created_at") or task.get("createdAt") or ""
    
    tasks.sort(key=get_sort_key, reverse=True)
    
    notifs = [
        {
            "id": t.get("id"),
            "status": t.get("status"),
            "updated_at": t.get("updated_at") or t.get("updatedAt") or t.get("created_at") or t.get("createdAt"),
        }
        for t in tasks[:20]
    ]
    return {"notifications": notifs}


class EventIn(BaseModel):
    type: str
    metadata: dict


class WorkflowSetupIn(BaseModel):
    type: str
    config: dict


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


@app.post("/api/workflows")
async def setup_workflow(workflow: WorkflowSetupIn, token: str = Depends(_get_token)):
    """Set up a new workflow automation."""
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    
    # Map workflow types to event types and create appropriate events
    workflow_configs = {
        # Productivity
        "chief-of-staff": {
            "event_type": "workflow.chief_of_staff.setup",
            "description": "Personal executive assistant for task and project management"
        },
        "news": {
            "event_type": "workflow.news.setup",
            "description": "Daily news intelligence briefing"
        },
        "research": {
            "event_type": "workflow.research.setup", 
            "description": "Automated research assistant"
        },
        "email-commander": {
            "event_type": "workflow.email.setup",
            "description": "Smart email automation and management"
        },
        "project": {
            "event_type": "workflow.project.setup",
            "description": "Project organization and tracking"
        },
        "calendar-optimizer": {
            "event_type": "workflow.calendar.setup",
            "description": "Smart calendar and time management"
        },
        "document-ai": {
            "event_type": "workflow.document_ai.setup",
            "description": "AI-powered document processing and intelligence"
        },
        
        # Health & Fitness
        "calorie-tracker": {
            "event_type": "workflow.nutrition.setup",
            "description": "Smart calorie and nutrition tracking"
        },
        "fitness-coach": {
            "event_type": "workflow.fitness.setup",
            "description": "AI fitness coach and workout planning"
        },
        "sleep-optimizer": {
            "event_type": "workflow.sleep.setup",
            "description": "Sleep tracking and optimization"
        },
        
        # Lifestyle
        "dream-trip": {
            "event_type": "workflow.travel.setup",
            "description": "Dream trip planning and travel intelligence"
        },
        "journal": {
            "event_type": "workflow.journal.setup",
            "description": "Daily journaling with smart prompts"
        },
        "home-automation": {
            "event_type": "workflow.home_automation.setup",
            "description": "Smart home automation and control"
        },
        
        # Business
        "market": {
            "event_type": "workflow.market.setup",
            "description": "Market and investment intelligence tracking"
        },
        "customer-success": {
            "event_type": "workflow.customer_success.setup",
            "description": "Automated customer success and satisfaction monitoring"
        },
        "sales-pipeline": {
            "event_type": "workflow.sales.setup",
            "description": "Sales pipeline automation and lead management"
        },
        
        # Creative
        "content-creator": {
            "event_type": "workflow.content.setup",
            "description": "Automated content creation and publishing pipeline"
        },
        "build-something": {
            "event_type": "workflow.development.setup",
            "description": "AI-powered development workflow from idea to deployment"
        },
        "learning": {
            "event_type": "workflow.learning.setup",
            "description": "Learning acceleration and skill development tracking"
        },
        "social-media": {
            "event_type": "workflow.social_media.setup",
            "description": "Social media automation and management"
        }
    }
    
    if workflow.type not in workflow_configs:
        raise HTTPException(status_code=400, detail=f"Unknown workflow type: {workflow.type}")
    
    config = workflow_configs[workflow.type]
    
    # Create the workflow setup event
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "workflow_setup",
        "type": config["event_type"],
        "metadata": {
            "workflow_type": workflow.type,
            "description": config["description"],
            "config": workflow.config,
            "user_email": workflow.config.get("email"),
            "setup_source": "landing_page"
        },
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{API_BASE}/events", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    # Also create a context hub space if needed
    if workflow.type in ["research", "project"]:
        try:
            context_payload = {
                "name": f"{workflow.type.title()} - {workflow.config.get('topics', workflow.config.get('description', 'New Space'))[:50]}",
                "content": f"# {workflow.type.title()} Workspace\n\nCreated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n\n## Configuration\n\n{workflow.config}\n\n## Notes\n\nThis space was automatically created by Lightning workflow setup.",
                "folder_id": None
            }
            context_resp = requests.post(f"{API_BASE}/context/documents", json=context_payload, headers=headers)
        except Exception as e:
            # Don't fail the workflow setup if context creation fails
            logging.warning(f"Failed to create context space: {e}")
    
    return {
        "status": "workflow_setup_initiated",
        "workflow_type": workflow.type,
        "message": f"{config['description']} setup has been initiated. You'll receive confirmation via email shortly."
    }


# Context Hub endpoints
@app.get("/context", response_class=HTMLResponse)
async def context_page(request: Request):
    """Context hub management page."""
    username = getattr(request.state, "username", "User")
    # Check if enhanced view is requested
    enhanced = request.query_params.get("enhanced", "false") == "true"
    template = "context_enhanced.html" if enhanced else "context.html"
    return templates.TemplateResponse(template, {
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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings and configuration page."""
    username = getattr(request.state, "username", "User")
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": username,
        "active_page": "settings"
    })


@app.get("/api/context/status")
async def context_status(request: Request, token: str = Depends(_get_token)):
    """Get user's context hub status."""
    username = getattr(request.state, "username", "demo-user")
    headers = _api_headers(token, username)
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
async def get_folders(request: Request, token: str = Depends(_get_token)):
    """Get user's folder structure."""
    username = getattr(request.state, "username", "demo-user")
    headers = _api_headers(token, username)
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


@app.get("/api/context/documents/{document_id}")
async def get_document(document_id: str, request: Request, token: str = Depends(_get_token)):
    """Get a specific document from user's context hub."""
    username = getattr(request.state, "username", "demo-user")
    headers = _api_headers(token, username)
    resp = requests.get(f"{API_BASE}/context/documents/{document_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.put("/api/context/documents/{document_id}")
async def update_document(document_id: str, doc: DocumentIn, request: Request, token: str = Depends(_get_token)):
    """Update a document in user's context hub."""
    username = getattr(request.state, "username", "demo-user")
    headers = _api_headers(token, username)
    payload = {
        "name": doc.name,
        "content": doc.content
    }
    resp = requests.put(f"{API_BASE}/context/documents/{document_id}", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.delete("/api/context/documents/{document_id}")
async def delete_document(document_id: str, token: str = Depends(_get_token)):
    """Delete a document from user's context hub."""
    headers = _api_headers(token)
    resp = requests.delete(f"{API_BASE}/context/documents/{document_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "deleted"}


@app.patch("/api/context/documents/{document_id}")
async def rename_document(document_id: str, name: dict, token: str = Depends(_get_token)):
    """Rename a document in user's context hub."""
    headers = _api_headers(token)
    resp = requests.patch(f"{API_BASE}/context/documents/{document_id}", json=name, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class FolderIn(BaseModel):
    name: str
    parent_id: Optional[str] = None


@app.post("/api/context/folders")
async def create_folder(folder: FolderIn, request: Request, token: str = Depends(_get_token)):
    """Create a new folder in user's context hub."""
    username = getattr(request.state, "username", "demo-user")
    headers = _api_headers(token, username)
    payload = {
        "name": folder.name,
        "parent_id": folder.parent_id
    }
    resp = requests.post(f"{API_BASE}/context/folders", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.delete("/api/context/folders/{folder_id}")
async def delete_folder(folder_id: str, token: str = Depends(_get_token)):
    """Delete a folder from user's context hub."""
    headers = _api_headers(token)
    resp = requests.delete(f"{API_BASE}/context/folders/{folder_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "deleted"}


@app.patch("/api/context/folders/{folder_id}")
async def rename_folder(folder_id: str, name: dict, token: str = Depends(_get_token)):
    """Rename a folder in user's context hub."""
    headers = _api_headers(token)
    resp = requests.patch(f"{API_BASE}/context/folders/{folder_id}", json=name, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/context/folders/{folder_id}/guide")
async def get_folder_guide(folder_id: str, token: str = Depends(_get_token)):
    """Get the Index Guide for a specific folder."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/folders/{folder_id}/guide", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/context/guide")
async def get_guide_file(token: str = Depends(_get_token)):
    """Get the INDEX_GUIDE.md file content."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/guide", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.put("/api/context/guide")
async def update_guide_file(content: dict, token: str = Depends(_get_token)):
    """Update the INDEX_GUIDE.md file content."""
    headers = _api_headers(token)
    resp = requests.put(f"{API_BASE}/context/guide", json=content, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Timeline API endpoints
@app.get("/api/context/timeline/snapshots")
async def get_timeline_snapshots(token: str = Depends(_get_token)):
    """Get timeline snapshots for context hub history."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/timeline/snapshots", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/context/timeline/state/{snapshot_id}")
async def get_timeline_state(snapshot_id: str, token: str = Depends(_get_token)):
    """Get historical state for a specific snapshot."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/context/timeline/state/{snapshot_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class RestoreRequest(BaseModel):
    item_id: str
    item_type: str  # 'document' or 'folder'
    snapshot_id: str
    overwrite: bool = False


@app.post("/api/context/timeline/restore")
async def restore_timeline_item(restore_req: RestoreRequest, token: str = Depends(_get_token)):
    """Restore an item from timeline to current state."""
    headers = _api_headers(token)
    payload = {
        "item_id": restore_req.item_id,
        "item_type": restore_req.item_type,
        "snapshot_id": restore_req.snapshot_id,
        "overwrite": restore_req.overwrite
    }
    resp = requests.post(f"{API_BASE}/context/timeline/restore", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Instructions API endpoints
@app.get("/api/instructions")
async def list_instructions(request: Request, token: str = Depends(_get_token)):
    """Get list of user instructions."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
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
async def create_instruction(instruction: InstructionIn, request: Request, token: str = Depends(_get_token)):
    """Create a new instruction."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    payload = instruction.dict()
    resp = requests.post(f"{API_BASE}/instructions", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.put("/api/instructions/{instruction_id}")
async def update_instruction(instruction_id: str, instruction: InstructionIn, request: Request, token: str = Depends(_get_token)):
    """Update an existing instruction."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    payload = instruction.dict()
    resp = requests.put(f"{API_BASE}/instructions/{instruction_id}", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.delete("/api/instructions/{instruction_id}")
async def delete_instruction(instruction_id: str, request: Request, token: str = Depends(_get_token)):
    """Delete an instruction."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    resp = requests.delete(f"{API_BASE}/instructions/{instruction_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "deleted"}


@app.patch("/api/instructions/{instruction_id}/toggle")
async def toggle_instruction(instruction_id: str, request: Request, token: str = Depends(_get_token)):
    """Toggle instruction enabled/disabled status."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    resp = requests.patch(f"{API_BASE}/instructions/{instruction_id}/toggle", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Plan API endpoints
@app.get("/api/plans/instruction/{instruction_id}")
async def get_plan_by_instruction(instruction_id: str, request: Request, token: str = Depends(_get_token)):
    """Get the latest plan for a specific instruction."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    resp = requests.get(f"{API_BASE}/plans/instruction/{instruction_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/plans/{plan_id}/critique")
async def critique_plan(plan_id: str, critique: dict, request: Request, token: str = Depends(_get_token)):
    """Submit a critique for a plan and generate a revised plan."""
    username = getattr(request.state, "username", None)
    headers = _api_headers(token, username)
    resp = requests.post(f"{API_BASE}/plans/{plan_id}/critique", json=critique, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Events API endpoints
@app.get("/api/events/types")
async def get_event_types(token: str = Depends(_get_token)):
    """Get available event types."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/events/types", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


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


# Chat API endpoints
@app.get("/api/chats")
async def get_chat_threads(request: Request, limit: int = 50, token: str = Depends(_get_token)):
    """Get list of chat threads for the current user."""
    username = getattr(request.state, "username", "local-user")
    headers = _api_headers(token, username)
    params = {"limit": limit}
    resp = requests.get(f"{API_BASE}/chats", headers=headers, params=params)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/chats/{chat_id}")
async def get_chat_thread(chat_id: str, request: Request, token: str = Depends(_get_token)):
    """Get a specific chat thread."""
    username = getattr(request.state, "username", "local-user")
    headers = _api_headers(token, username)
    resp = requests.get(f"{API_BASE}/chats/{chat_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


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


@app.get("/logout")
async def logout(request: Request):
    """Logout endpoint - clears session and redirects to auth gateway."""
    request.session.clear()
    
    # Redirect to auth gateway logout
    gateway_base = _resolve_gateway_url(request)
    logout_url = f"{gateway_base}/logout"
    resp = RedirectResponse(url=logout_url)
    resp.delete_cookie("auth_token")
    return resp


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
