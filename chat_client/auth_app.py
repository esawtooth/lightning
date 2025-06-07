#!/usr/bin/env python3
"""
Authentication gateway for the Lightning chat application.
Users must authenticate before accessing the Chainlit chat interface.
"""

import os
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

import jwt
import requests
from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie
from common.jwt_utils import verify_token as _verify_token
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

# Configuration
AUTH_API_URL = os.environ.get("AUTH_API_URL", "")  # Azure Function auth endpoint
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "your-secret-key-change-in-production")

# Setup
app = FastAPI(title="Lightning Chat Authentication")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def _refresh_cookie(request: Request, call_next):
    response = await call_next(request)
    new_token = getattr(request.state, "new_token", None)
    if new_token:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        secure_cookie = (request.url.scheme == "https" or forwarded_proto == "https")
        response.set_cookie(
            key="auth_token",
            value=new_token,
            max_age=3600,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
        )
    return response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple in-memory rate limiting
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10
_rate_limit: dict[str, deque] = defaultdict(deque)

CSRF_SESSION_KEY = "csrf_token"


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    window = _rate_limit[ip]
    while window and window[0] < now - RATE_LIMIT_WINDOW:
        window.popleft()
    if len(window) >= RATE_LIMIT_MAX:
        return True
    window.append(now)
    return False


def _generate_csrf_token(request: Request) -> str:
    token = secrets.token_hex(16)
    request.session[CSRF_SESSION_KEY] = token
    return token


def _verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or expected != token:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return username if valid."""
    try:
        return _verify_token(token)
    except Exception as e:
        logger.warning(f"Invalid token: {e}")
        return None


def _resolve_chainlit_url(request: Request) -> str:
    """Return the base URL for the Chainlit service."""
    configured = os.environ.get("CHAINLIT_URL")
    if configured:
        return configured

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.hostname or "localhost")
    host = host.split(":")[0]
    return f"{scheme}://{host}/chat"


async def get_current_user(request: Request) -> Optional[str]:
    """Get current authenticated user from session or cookie."""
    # Check session first
    username = request.session.get("username")
    if username:
        return username
    
    # Check JWT cookie
    token = request.cookies.get("auth_token")
    if token:
        username = verify_token(token)
        if username:
            # Refresh the token if it expires within 5 minutes
            try:
                payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
                exp_ts = payload.get("exp", 0)
                if exp_ts - time.time() < 300 and AUTH_API_URL:
                    try:
                        resp = requests.post(
                            f"{AUTH_API_URL}/refresh",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            new_token = resp.json().get("token")
                            if new_token:
                                request.state.new_token = new_token
                                token = new_token
                    except requests.RequestException as e:
                        logger.error(f"Token refresh failed: {e}")
            except Exception:
                pass
            request.session["username"] = username
            return username
    
    return None


@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, username: Optional[str] = Depends(get_current_user)):
    """Display login page or redirect to chat if already authenticated."""
    if username:
        return RedirectResponse(url="/chat", status_code=302)

    csrf_token = _generate_csrf_token(request)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": request.query_params.get("error"),
        "csrf_token": csrf_token,
    })


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(default="")
):
    """Handle user login."""
    if not AUTH_API_URL:
        raise HTTPException(status_code=500, detail="Authentication service not configured")

    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    _verify_csrf(request, csrf_token)
    
    try:
        # Call Azure Function auth endpoint
        auth_data = {"username": username, "password": password}
        response = requests.post(f"{AUTH_API_URL}/login", json=auth_data, timeout=10)
        
        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get("token")
            
            if token and verify_token(token):
                # Set session and secure cookie
                request.session["username"] = username
                
                redirect_response = RedirectResponse(url="/chat", status_code=302)
                forwarded_proto = request.headers.get("x-forwarded-proto")
                secure_cookie = (request.url.scheme == "https" or forwarded_proto == "https")
                redirect_response.set_cookie(
                    key="auth_token",
                    value=token,
                    max_age=3600,  # 1 hour
                    httponly=True,
                    secure=secure_cookie,
                    samesite="lax"
                )
                
                logger.info(f"User {username} logged in successfully")
                return redirect_response
            else:
                logger.error("Invalid token received from auth service")
                return RedirectResponse(url="/?error=auth_failed", status_code=302)
        
        elif response.status_code == 401:
            return RedirectResponse(url="/?error=invalid_credentials", status_code=302)
        elif response.status_code == 403:
            # Handle waitlist and rejected users
            try:
                error_data = response.json()
                status = error_data.get("status", "unknown")
                if status == "waitlist":
                    return RedirectResponse(url="/?error=account_pending", status_code=302)
                elif status == "rejected":
                    return RedirectResponse(url="/?error=account_rejected", status_code=302)
                else:
                    return RedirectResponse(url="/?error=account_not_approved", status_code=302)
            except:
                return RedirectResponse(url="/?error=account_not_approved", status_code=302)
        else:
            logger.error(f"Auth service error: {response.status_code} - {response.text}")
            return RedirectResponse(url="/?error=service_error", status_code=302)
            
    except requests.RequestException as e:
        logger.error(f"Failed to connect to auth service: {e}")
        return RedirectResponse(url="/?error=service_unavailable", status_code=302)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Display registration page."""
    csrf_token = _generate_csrf_token(request)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": request.query_params.get("error"),
        "csrf_token": csrf_token,
    })


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    email: str = Form(...),
    csrf_token: str = Form(default="")
):
    """Handle user registration."""
    if not AUTH_API_URL:
        raise HTTPException(status_code=500, detail="Authentication service not configured")

    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    _verify_csrf(request, csrf_token)
    
    if password != confirm_password:
        return RedirectResponse(url="/register?error=password_mismatch", status_code=302)

    if not _is_strong_password(password):
        return RedirectResponse(url="/register?error=password_too_short", status_code=302)

    if not email:
        return RedirectResponse(url="/register?error=email_required", status_code=302)
    
    try:
        # Call Azure Function auth endpoint
        auth_data = {"username": username, "password": password, "email": email}
        response = requests.post(f"{AUTH_API_URL}/register", json=auth_data, timeout=10)
        
        if response.status_code == 201:
            logger.info(f"User {username} registered successfully and placed on waitlist")
            return RedirectResponse(url="/?message=registration_waitlist", status_code=302)
        elif response.status_code == 409:
            return RedirectResponse(url="/register?error=username_exists", status_code=302)
        else:
            logger.error(f"Registration error: {response.status_code} - {response.text}")
            return RedirectResponse(url="/register?error=service_error", status_code=302)
            
    except requests.RequestException as e:
        logger.error(f"Failed to connect to auth service: {e}")
        return RedirectResponse(url="/register?error=service_unavailable", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    """Handle user logout."""
    request.session.clear()
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("auth_token")
    
    return response


@app.get("/chat")
async def chat_redirect(request: Request, username: Optional[str] = Depends(get_current_user)):
    """Redirect to Chainlit chat interface if authenticated."""
    if not username:
        return RedirectResponse(url="/", status_code=302)

    chainlit_url = _resolve_chainlit_url(request)
    return RedirectResponse(url=chainlit_url, status_code=302)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, username: Optional[str] = Depends(get_current_user)):
    """Display admin panel for user management."""
    if not username:
        return RedirectResponse(url="/", status_code=302)
    
    # Check if user is admin (verify JWT token role)
    token = request.cookies.get("auth_token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    
    try:
        if JWT_SIGNING_KEY:
            payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
            user_role = payload.get("role", "user")
            
            if user_role != "admin":
                return RedirectResponse(url="/?error=admin_required", status_code=302)
        else:
            return RedirectResponse(url="/?error=service_error", status_code=302)
    except:
        return RedirectResponse(url="/?error=invalid_token", status_code=302)
    
    # Fetch user stats for initial display
    pending_count = 0
    approved_count = 0
    rejected_count = 0
    
    if AUTH_API_URL:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(f"{AUTH_API_URL}/pending", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                pending_count = data.get("pending_count", 0)
                approved_count = data.get("approved_count", 0)
                rejected_count = data.get("rejected_count", 0)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch user stats: {e}")
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "username": username,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "error": request.query_params.get("error"),
        "message": request.query_params.get("message")
    })


@app.post("/admin/approve")
async def approve_user(
    request: Request,
    target_username: str = Form(...),
    action: str = Form(...),  # approve or reject
    username: Optional[str] = Depends(get_current_user)
):
    """Handle user approval/rejection by admin."""
    if not username:
        return RedirectResponse(url="/", status_code=302)
    
    # Verify admin token
    token = request.cookies.get("auth_token")
    if not token or not JWT_SIGNING_KEY:
        return RedirectResponse(url="/admin?error=invalid_token", status_code=302)
    
    try:
        payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
        if payload.get("role") != "admin":
            return RedirectResponse(url="/admin?error=admin_required", status_code=302)
    except:
        return RedirectResponse(url="/admin?error=invalid_token", status_code=302)
    
    if action not in ["approve", "reject"]:
        return RedirectResponse(url="/admin?error=invalid_action", status_code=302)
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        approval_data = {"username": target_username, "action": action}
        response = requests.post(f"{AUTH_API_URL}/approve", json=approval_data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            message = f"user_{action}d"
            return RedirectResponse(url=f"/admin?message={message}", status_code=302)
        else:
            return RedirectResponse(url="/admin?error=approval_failed", status_code=302)
            
    except requests.RequestException as e:
        logger.error(f"Failed to {action} user: {e}")
        return RedirectResponse(url="/admin?error=service_unavailable", status_code=302)


# Admin API endpoints for the admin panel
@app.get("/admin/api/users")
async def get_all_users(request: Request, username: Optional[str] = Depends(get_current_user)):
    """API endpoint to get all users with stats for admin panel."""
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Verify admin token
    token = request.cookies.get("auth_token")
    if not token or not JWT_SIGNING_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    try:
        payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    if not AUTH_API_URL:
        raise HTTPException(status_code=500, detail="Authentication service not configured")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{AUTH_API_URL}/pending", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            users = data.get("users", [])
            
            # Calculate stats
            pending_count = sum(1 for user in users if user.get("status") == "waitlist")
            approved_count = sum(1 for user in users if user.get("status") == "approved")
            rejected_count = sum(1 for user in users if user.get("status") == "rejected")
            
            return {
                "users": users,
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count
            }
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch users")
            
    except requests.RequestException as e:
        logger.error(f"Failed to fetch users: {e}")
        raise HTTPException(status_code=500, detail="Service unavailable")


@app.post("/admin/api/user-action")
async def handle_user_action(
    request: Request,
    action_data: dict,
    username: Optional[str] = Depends(get_current_user)
):
    """API endpoint to approve/reject users."""
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Verify admin token
    token = request.cookies.get("auth_token")
    if not token or not JWT_SIGNING_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    try:
        payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    action = action_data.get("action")
    user_id = action_data.get("user_id")
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    
    if not AUTH_API_URL:
        raise HTTPException(status_code=500, detail="Authentication service not configured")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        approval_data = {"user_id": user_id, "action": action}
        response = requests.post(f"{AUTH_API_URL}/approve", json=approval_data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return {"status": "success", "message": f"User {action}d successfully"}
        else:
            error_detail = f"Failed to {action} user"
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", error_detail)
            except:
                pass
            raise HTTPException(status_code=response.status_code, detail=error_detail)
            
    except requests.RequestException as e:
        logger.error(f"Failed to {action} user: {e}")
        raise HTTPException(status_code=500, detail="Service unavailable")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=443)
