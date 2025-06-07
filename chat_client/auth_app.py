#!/usr/bin/env python3
"""Simplified authentication gateway using Azure Entra ID."""
import os
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import msal
from common.jwt_utils import verify_token

AAD_CLIENT_ID = os.environ.get("AAD_CLIENT_ID") or os.environ.get("AZURE_CLIENT_ID")
AAD_TENANT_ID = os.environ.get("AAD_TENANT_ID") or os.environ.get("AZURE_TENANT_ID")
AAD_CLIENT_SECRET = os.environ.get("AAD_CLIENT_SECRET") or os.environ.get("AZURE_CLIENT_SECRET")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")

if not (AAD_CLIENT_ID and AAD_TENANT_ID and AAD_CLIENT_SECRET):
    logging.warning("AAD configuration incomplete")

auth_app = msal.ConfidentialClientApplication(
    AAD_CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{AAD_TENANT_ID}",
    client_credential=AAD_CLIENT_SECRET,
)

SCOPES = ["User.Read"]

app = FastAPI(title="Lightning Chat Authentication")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
templates = Jinja2Templates(directory="templates")


@app.get("/login")
async def login(request: Request):
    """Redirect user to Azure login."""
    redirect_uri = request.url_for("auth_callback")
    auth_url = auth_app.get_authorization_request_url(SCOPES, redirect_uri=redirect_uri)
    return RedirectResponse(auth_url)


@app.get("/callback")
async def auth_callback(request: Request):
    """Process the authentication response from Azure AD."""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    redirect_uri = request.url_for("auth_callback")
    result = auth_app.acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=redirect_uri)
    token = result.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication failed")
    try:
        user_id = verify_token(token)
        request.session["user_id"] = user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    resp = RedirectResponse(url="/chat")
    resp.set_cookie(
        key="auth_token",
        value=token,
        max_age=3600,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return resp


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    resp = RedirectResponse(url="/")
    resp.delete_cookie("auth_token")
    return resp


def _resolve_chainlit_url(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = forwarded or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    return f"{scheme}://{host}/chat"


@app.get("/chat")
async def chat_redirect(request: Request):
    token = request.cookies.get("auth_token")
    if not token:
        return RedirectResponse(url="/login")
    try:
        verify_token(token)
    except Exception:
        return RedirectResponse(url="/login")
    return RedirectResponse(_resolve_chainlit_url(request))


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
