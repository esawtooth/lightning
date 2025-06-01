import os
from datetime import datetime
from typing import Optional

import jwt
import logging
import requests
import chainlit as cl
from fastapi import HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from chainlit.server import app as fastapi_app
from dashboard.app import app as dashboard_app

EVENT_API_URL = os.environ.get("EVENT_API_URL")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY")
AUTH_GATEWAY_URL = os.environ.get("AUTH_GATEWAY_URL", "http://localhost:8000")



def verify_user_token(token: str) -> Optional[str]:
    """Verify JWT token and return username if valid."""
    if not JWT_SIGNING_KEY:
        logging.error("JWT_SIGNING_KEY not configured")
        return None
    
    try:
        payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if username and payload.get("exp", 0) > datetime.utcnow().timestamp():
            return username
    except jwt.InvalidTokenError as e:
        logging.warning(f"Invalid token: {e}")
    
    return None


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


@fastapi_app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Authentication middleware for all Chainlit routes."""
    # Allow health checks and static assets
    if request.url.path in ["/health", "/dashboard"] or request.url.path.startswith("/static"):
        return await call_next(request)
    
    # Check authentication
    username = await authenticate_user(request)
    if not username:
        # Redirect to auth gateway
        redirect_url = f"{AUTH_GATEWAY_URL}/?redirect={request.url}"
        return RedirectResponse(url=redirect_url)
    
    # Store username in request state for use in Chainlit handlers
    request.state.username = username
    
    # For Chainlit WebSocket connections, we need to handle auth differently
    response = await call_next(request)
    return response


@cl.on_chat_start
async def start():
    """Initialize chat session with user context."""
    # Try to get user from various sources
    user = "User"  # Default fallback
    
    # The username will be available through Chainlit's session context
    try:
        # Get from Chainlit session if available
        if hasattr(cl.context, 'session') and cl.context.session:
            user = getattr(cl.context.session, 'username', user)
    except:
        pass
    
    welcome_message = f"""
🌟 **Welcome to Lightning Chat, {user}!**

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
        "service": "lightning-chat",
        "timestamp": datetime.utcnow().isoformat()
    }


@fastapi_app.post("/notify")
async def notify(payload: dict):
    """Forward a message to the current Chainlit session."""
    user_id = payload.get("user_id")
    message = payload.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message required")

    await cl.Message(content=message, author=user_id or "assistant").send()
    return {"status": "ok"}

# Expose the dashboard under /dashboard on the Chainlit FastAPI app
fastapi_app.mount("/dashboard", dashboard_app)
