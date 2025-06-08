import os
from datetime import datetime
from typing import Optional

from common.jwt_utils import verify_token
import logging
import requests
import chainlit as cl
from fastapi import HTTPException, Depends
from fastapi.responses import RedirectResponse
from starlette.requests import Request
from chainlit.server import app as fastapi_app
from dashboard.app import app as dashboard_app
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Only for type hints, avoid hard dependency for tests
    from chainlit.session import WebsocketSession

SESSION_MAP: dict[str, 'WebsocketSession'] = {}


def get_session_by_user(user_id: str):
    """Return the Chainlit session for the given user, if any."""
    return SESSION_MAP.get(user_id)

EVENT_API_URL = os.environ.get("EVENT_API_URL")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
AUTH_GATEWAY_URL = os.environ.get("AUTH_GATEWAY_URL")
CHAINLIT_URL = os.environ.get("CHAINLIT_URL")
NOTIFY_TOKEN = os.environ.get("NOTIFY_TOKEN")



def verify_user_token(token: str) -> Optional[str]:
    try:
        return verify_token(token)
    except Exception as e:
        logging.warning(f"Invalid token: {e}")
        return None


def _resolve_request_url(request: Request) -> str:
    """Return the externally accessible URL for the given request."""
    base = CHAINLIT_URL.rstrip("/") if CHAINLIT_URL else None
    if base:
        return f"{base}{request.url.path}"

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.hostname or "localhost")
    return f"{scheme}://{host}{request.url.path}"


def _resolve_gateway_url(request: Request) -> str:
    """Return the URL of the authentication gateway for the request."""
    base = AUTH_GATEWAY_URL.rstrip("/") if AUTH_GATEWAY_URL else None
    if base:
        return base

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.hostname or "localhost")
    host = host.split(":")[0]
    return f"{scheme}://{host}"


async def authenticate_user(request: Request) -> Optional[str]:
    """Authenticate user from session or token."""
    # Check for auth token in cookies
    token = request.cookies.get("auth_token")
    if token:
        username = verify_user_token(token)
        if username:
            return username
    
    # If no valid authentication, redirect to auth gateway
    return None


if hasattr(fastapi_app, "middleware"):
    @fastapi_app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """Authentication middleware for all Chainlit routes."""
        # Allow health checks and static assets
        if request.url.path in ["/health", "/dashboard"] or request.url.path.startswith("/static"):
            return await call_next(request)

        # Check authentication
        username = await authenticate_user(request)
        if not username:
            # Redirect to auth gateway with externally visible URL
            target_url = _resolve_request_url(request)
            gateway_base = _resolve_gateway_url(request)
            redirect_url = f"{gateway_base}/?redirect={target_url}"
            return RedirectResponse(url=redirect_url)

        # Store username in request state for use in Chainlit handlers
        request.state.username = username

        # For Chainlit WebSocket connections, we need to handle auth differently
        response = await call_next(request)
        return response


@cl.on_chat_start
async def start():
    """Initialize chat session with user context."""
    username = None

    # Try to get from the authenticated request
    try:
        username = getattr(getattr(cl.context, "request", None).state, "username", None)
    except Exception:
        username = None

    # Fallback to any existing session username
    if not username:
        try:
            if hasattr(cl.context, "session") and cl.context.session:
                username = getattr(cl.context.session, "username", None)
        except Exception:
            username = None

    if not username:
        username = "User"

    # Attach username to the session and store it globally
    try:
        if hasattr(cl.context, "session") and cl.context.session:
            cl.context.session.username = username
            SESSION_MAP[username] = cl.context.session
    except Exception:
        pass
    
    welcome_message = f"""
🌟 **Welcome to Vextir Chat, {username}!**

I'm your AI assistant, ready to help you with:
- Answering questions
- Code assistance
- Repository analysis
- General conversation

What would you like to explore today?
    """.strip()
    
    await cl.Message(
        content=welcome_message,
        author="Assistant"
    ).send()


@cl.on_chat_end
async def end():
    """Cleanup session when the user disconnects."""
    username = getattr(getattr(cl.context, "session", None), "username", None)
    if username:
        SESSION_MAP.pop(username, None)


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user message and queue a chat event."""
    if not EVENT_API_URL:
        await cl.Message(content="EVENT_API_URL not configured", author="system").send()
        return
    if not AUTH_TOKEN:
        await cl.Message(content="AUTH_TOKEN not configured", author="system").send()
        return

    # Get username from various possible sources
    username = "anonymous"
    try:
        # Try to get from Chainlit session
        if hasattr(cl.context, 'session') and cl.context.session:
            username = getattr(cl.context.session, 'username', username)
        # Could also try to get from request context if available
    except:
        pass
    
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "chainlit",
        "type": "llm.chat",
        "user_id": username,
        "metadata": {
            "messages": [{"role": "user", "content": message.content}]
        },
    }

    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    try:
        resp = requests.post(EVENT_API_URL, json=event, headers=headers)
        if not 200 <= resp.status_code < 300:
            logging.warning("Event API returned status %s: %s", resp.status_code, resp.text)
    except Exception as e:
        await cl.Message(content=f"Failed to send event: {e}", author="system").send()
        return

    await cl.Message(content="Message queued successfully! 🚀", author="system").send()


@fastapi_app.get("/health")
async def health_check():
    """Health check endpoint for the chat service."""
    return {
        "status": "healthy",
        "service": "vextir-chat",
        "timestamp": datetime.utcnow().isoformat()
    }


@fastapi_app.post("/notify")
async def notify(request: Request, payload: dict):
    """Forward a message to the current Chainlit session."""
    # Authorization via session or bearer token
    auth_header = request.headers.get("Authorization")
    authorized = False
    if auth_header:
        if NOTIFY_TOKEN and auth_header == f"Bearer {NOTIFY_TOKEN}":
            authorized = True
        elif auth_header.startswith("Bearer ") and verify_user_token(auth_header.split(" ", 1)[1]):
            authorized = True
    else:
        user = await authenticate_user(request)
        if user:
            authorized = True

    if not authorized:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = payload.get("user_id")
    message = payload.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message required")

    session = get_session_by_user(user_id) if user_id else None
    if user_id and session is None:
        raise HTTPException(status_code=404, detail="No active session")

    await cl.Message(content=message, author=user_id or "assistant").send(
        session_id=session.id if session else None
    )
    return {"status": "ok"}

# Expose the dashboard under /dashboard on the Chainlit FastAPI app
fastapi_app.mount("/dashboard", dashboard_app)
