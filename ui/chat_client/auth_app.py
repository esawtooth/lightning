#!/usr/bin/env python3
"""Simplified authentication gateway using Azure Entra ID with waitlist approval."""
import os
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import requests
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import msal
from common.jwt_utils import verify_token

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AAD_CLIENT_ID = (
    os.environ.get("AAD_CLIENT_ID")
    or os.environ.get("ARM_CLIENT_ID")
    or os.environ.get("AZURE_CLIENT_ID")
)
AAD_TENANT_ID = (
    os.environ.get("AAD_TENANT_ID")
    or os.environ.get("ARM_TENANT_ID")
    or os.environ.get("AZURE_TENANT_ID")
)
AAD_CLIENT_SECRET = (
    os.environ.get("AAD_CLIENT_SECRET")
    or os.environ.get("ARM_CLIENT_SECRET")
    or os.environ.get("AZURE_CLIENT_SECRET")
)
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
AUTH_API_URL = os.environ.get("AUTH_API_URL", "/api")
# Optional override for external URL of this gateway
AUTH_GATEWAY_URL = os.environ.get("AUTH_GATEWAY_URL")

# Debug logging for environment variables
logger.info(f"AAD_CLIENT_ID configured: {bool(AAD_CLIENT_ID)}")
logger.info(f"AAD_TENANT_ID configured: {bool(AAD_TENANT_ID)}")
logger.info(f"AAD_CLIENT_SECRET configured: {bool(AAD_CLIENT_SECRET)}")

if not (AAD_CLIENT_ID and AAD_TENANT_ID and AAD_CLIENT_SECRET):
    logger.error("AAD configuration incomplete - this will cause authentication failures!")
    logger.error(f"Missing: AAD_CLIENT_ID={bool(AAD_CLIENT_ID)}, AAD_TENANT_ID={bool(AAD_TENANT_ID)}, AAD_CLIENT_SECRET={bool(AAD_CLIENT_SECRET)}")

try:
    auth_app = msal.ConfidentialClientApplication(
        AAD_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AAD_TENANT_ID}",
        client_credential=AAD_CLIENT_SECRET,
    )
    logger.info("MSAL ConfidentialClientApplication created successfully")
except Exception as e:
    logger.error(f"Failed to create MSAL application: {e}")
    # Create a dummy auth_app to prevent import errors
    auth_app = None

# MSAL automatically adds "openid" and "profile" when needed. Explicitly
# requesting these reserved scopes results in a runtime error, so we only
# request the Microsoft Graph scope here.
SCOPES = ["User.Read"]

app = FastAPI(title="Vextir Chat Authentication")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory="templates")


async def check_user_approval(user_id: str) -> dict:
    """Check if user is approved to access the system."""
    try:
        resp = requests.get(
            f"{AUTH_API_URL.rstrip('/')}/auth/status/{user_id}",
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"status": "not_found", "approved": False}
    except Exception:
        return {"status": "error", "approved": False}


async def request_access(user_id: str, email: str, name: str = None) -> bool:
    """Request access for a new user."""
    try:
        resp = requests.post(
            f"{AUTH_API_URL.rstrip('/')}/auth/request",
            json={"user_id": user_id, "email": email, "name": name},
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Login page or redirect if already authenticated."""
    token = request.cookies.get("auth_token")
    if token:
        try:
            user_id = verify_token(token)
            user_status = await check_user_approval(user_id)
            if user_status.get("approved"):
                return RedirectResponse(url="/app")
            else:
                return RedirectResponse(url=request.url_for("waitlist_page"))
        except Exception:
            pass
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login")
async def login(request: Request):
    """Redirect user to Azure login or handle callback for legacy redirect."""
    # Check if MSAL is properly configured
    if auth_app is None:
        logger.error("MSAL not configured - cannot perform authentication")
        return RedirectResponse("/?error=service_unavailable", status_code=303)
    
    # If Azure AD redirected here with a code parameter, treat it as a callback
    if "code" in request.query_params:
        return await auth_callback(request)

    try:
        redirect_uri = _resolve_callback_url(request)
        logger.info(f"Resolved callback URI: {redirect_uri}")
        auth_url = auth_app.get_authorization_request_url(SCOPES, redirect_uri=redirect_uri)
        logger.info(f"Generated auth URL: {auth_url}")
        return RedirectResponse(auth_url)
    except Exception as e:
        logger.error(f"Failed to get authorization URL: {e}")
        logger.error(f"Request URL: {request.url}")
        logger.error(f"Request headers: {dict(request.headers)}")
        return RedirectResponse("/?error=auth_failed", status_code=303)


@app.get("/auth/login")
async def auth_login(request: Request):
    """Alias for /login route to handle frontend requests to /auth/login."""
    logger.info(f"Auth login request from {request.client.host if request.client else 'unknown'}")
    return await login(request)


@app.get("/callback")
async def auth_callback(request: Request):
    """Process the authentication response from Azure AD."""
    logger.info(f"Auth callback received from {request.client.host if request.client else 'unknown'}")
    
    # Check if MSAL is properly configured
    if auth_app is None:
        logger.error("MSAL not configured - cannot process authentication callback")
        return RedirectResponse("/?error=service_unavailable", status_code=303)
    
    code = request.query_params.get("code")
    if not code:
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")
        logger.error(f"Auth callback missing code. Error: {error}, Description: {error_description}")
        return RedirectResponse("/?error=auth_failed", status_code=303)
    
    try:
        redirect_uri = _resolve_callback_url(request)
        logger.info(f"Using redirect URI: {redirect_uri}")
        
        result = auth_app.acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=redirect_uri)
        if "error" in result:
            logger.error(f"MSAL token acquisition failed: {result.get('error_description', result.get('error'))}")
            return RedirectResponse("/?error=auth_failed", status_code=303)
    except Exception as e:
        logger.error(f"Exception during token acquisition: {e}")
        logger.error(f"Request URL: {request.url}")
        return RedirectResponse("/?error=service_unavailable", status_code=303)
    # Use the ID token for authentication. This token has our client ID as
    # the audience and can be validated locally. If it's missing, fall back to
    # the access token for backwards compatibility.
    token = result.get("id_token") or result.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    try:
        user_id = verify_token(token)
        request.session["user_id"] = user_id
        
        # Get user info from AAD token for registration
        id_claims = result.get("id_token_claims", {})
        user_email = id_claims.get("email") or id_claims.get("preferred_username")
        user_name = id_claims.get("name")
        
        # Check if user is approved
        user_status = await check_user_approval(user_id)
        
        if user_status.get("approved"):
            # User is approved, set auth cookie and redirect to integrated UI
            resp = RedirectResponse(url="/app")
            resp.set_cookie(
                key="auth_token",
                value=token,
                max_age=3600,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="lax",
            )
            return resp
        else:
            # User not approved, automatically request access if new user
            if user_status.get("status") == "not_found" and user_email:
                await request_access(user_id, user_email, user_name)
            
            # Redirect to waitlist page
            return RedirectResponse(url=request.url_for("waitlist_page"))
            
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return RedirectResponse("/?error=auth_failed", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    resp = RedirectResponse(url="/")
    resp.delete_cookie("auth_token")
    return resp


@app.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page(request: Request):
    """Inform user that their access request is pending."""
    return templates.TemplateResponse("waitlist.html", {"request": request})


def _resolve_ui_url(request: Request) -> str:
    """Return external URL for the integrated UI."""
    if AUTH_GATEWAY_URL:
        base = AUTH_GATEWAY_URL.rstrip("/")
        return f"{base}/app"
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = forwarded or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    return f"{scheme}://{host}/app"


def _resolve_callback_url(request: Request) -> str:
    """Return external URL for the auth callback endpoint."""
    if AUTH_GATEWAY_URL:
        base = AUTH_GATEWAY_URL.rstrip("/")
        return f"{base}/auth/callback"
    
    # When mounted under /auth, we need to build the callback URL manually
    # because request.url_for() doesn't account for the mounting path
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = forwarded or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    port = request.url.port
    
    # Build the base URL
    if port and port not in (80, 443):
        base_url = f"{scheme}://{host}:{port}"
    else:
        base_url = f"{scheme}://{host}"
    
    # Add the callback path - since we're mounted at /auth, callback is at /auth/callback
    return f"{base_url}/auth/callback"


@app.get("/chat")
async def chat_redirect(request: Request):
    token = request.cookies.get("auth_token")
    if not token:
        return RedirectResponse(url="/login")
    try:
        user_id = verify_token(token)
        user_status = await check_user_approval(user_id)
        if not user_status.get("approved"):
            return RedirectResponse(url=request.url_for("waitlist_page"))
    except Exception:
        return RedirectResponse(url="/login")
    return RedirectResponse(_resolve_ui_url(request))


@app.post("/request-access")
async def manual_request_access(request: Request):
    """Manual access request for users who want to join the waitlist."""
    form = await request.form()
    email = form.get("email")
    name = form.get("name")
    
    if not email:
        return RedirectResponse("/?error=email_required", status_code=303)
    
    # For manual requests, we don't have an AAD user ID yet
    # Store the request with email as identifier
    success = await request_access(email, email, name)
    
    if success:
        return RedirectResponse("/?message=access_requested", status_code=303)
    else:
        return RedirectResponse("/?error=request_failed", status_code=303)


@app.post("/auth/request-access")
async def auth_request_access(request: Request):
    """Alias for /request-access route to handle frontend requests to /auth/request-access."""
    return await manual_request_access(request)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/auth/status")
async def auth_status():
    """Diagnostic endpoint to check authentication configuration."""
    return {
        "msal_configured": auth_app is not None,
        "aad_client_id_set": bool(AAD_CLIENT_ID),
        "aad_tenant_id_set": bool(AAD_TENANT_ID),
        "aad_client_secret_set": bool(AAD_CLIENT_SECRET),
        "auth_api_url": AUTH_API_URL,
        "auth_gateway_url": AUTH_GATEWAY_URL
    }


@app.get("/auth/test-callback-url")
async def test_callback_url(request: Request):
    """Test endpoint to verify callback URL resolution."""
    try:
        callback_url = _resolve_callback_url(request)
        return {
            "callback_url": callback_url,
            "request_url": str(request.url),
            "headers": dict(request.headers),
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "request_url": str(request.url),
            "headers": dict(request.headers),
            "success": False
        }
