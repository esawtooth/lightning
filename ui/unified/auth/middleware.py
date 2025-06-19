"""
Authentication middleware for Lightning Unified UI.
"""

import logging
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config import settings
from .utils import verify_token

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle authentication for all requests.
    """
    
    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/health",
        "/auth/login",
        "/auth/register",
        "/auth/callback",
        "/api/docs",
        "/api/redoc",
        "/openapi.json",
    }
    
    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = {
        "/static/",
        "/_next/",  # For Next.js if integrated
    }
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and check authentication."""
        
        # Check if path is public
        if self._is_public_path(request.url.path):
            return await call_next(request)
        
        # Get user from various sources
        user = await self._authenticate_request(request)
        
        if user:
            # Attach user to request state
            request.state.user = user
            request.state.user_id = user.get("id", user.get("username"))
            return await call_next(request)
        
        # Handle unauthenticated requests
        if request.url.path.startswith("/api/"):
            # API requests get 401
            return Response(
                content='{"detail": "Authentication required"}',
                status_code=401,
                headers={"Content-Type": "application/json"},
            )
        else:
            # Web requests get redirected to login
            return_url = str(request.url)
            login_url = f"/auth/login?return_to={return_url}"
            return RedirectResponse(url=login_url)
    
    def _is_public_path(self, path: str) -> bool:
        """Check if the path is public (no auth required)."""
        # Exact matches
        if path in self.PUBLIC_PATHS:
            return True
        
        # Prefix matches
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        
        # Development mode - allow all in local env
        if settings.app_env == "development" and settings.auth_provider == "local":
            return True
        
        return False
    
    async def _authenticate_request(self, request: Request) -> Optional[dict]:
        """
        Authenticate the request using various methods.
        
        Returns user dict if authenticated, None otherwise.
        """
        # 1. Check session
        user = request.session.get("user")
        if user:
            return user
        
        # 2. Check JWT token in cookie
        token = request.cookies.get("auth_token")
        if token:
            user_data = verify_token(token)
            if user_data:
                # Update session
                request.session["user"] = user_data
                return user_data
        
        # 3. Check Authorization header (for API requests)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            user_data = verify_token(token)
            if user_data:
                return user_data
        
        # 4. Check API key (for service-to-service)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # TODO: Validate API key
            return {"id": "service", "username": "api-service", "role": "service"}
        
        # 5. Development mode - auto-authenticate
        if settings.app_env == "development" and settings.auth_provider == "local":
            return {
                "id": "dev-user",
                "username": "developer",
                "email": "dev@lightning.ai",
                "role": "admin",
            }
        
        return None