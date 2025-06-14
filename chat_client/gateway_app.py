import os

from fastapi import FastAPI, Request, HTTPException, Response
from starlette.responses import RedirectResponse
import asyncio
import requests
from common.jwt_utils import verify_token

from auth_app import app as auth_app
from chainlit_app import fastapi_app as chat_app

app = FastAPI(title="Vextir Chat Gateway")

GITEA_URL = os.environ.get("GITEA_URL")

# Mount the auth and chat applications under separate routes
app.mount("/auth", auth_app)
app.mount("/chat", chat_app)

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to the authentication gateway."""
    return RedirectResponse(url="/auth")


@app.get("/register", include_in_schema=False)
async def register_root():
    """Legacy registration path for convenience."""
    return RedirectResponse(url="/auth/register")

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/repo", include_in_schema=False)
async def repo_redirect(request: Request):
    """Redirect the authenticated user to their Gitea repository."""
    if not GITEA_URL:
        raise HTTPException(status_code=404, detail="GITEA_URL not configured")

    token = request.cookies.get("auth_token")
    if not token:
        return RedirectResponse(url="/auth/login")

    try:
        user_id = verify_token(token)
    except Exception:
        return RedirectResponse(url="/auth/login")

    base = GITEA_URL.rstrip("/")
    return RedirectResponse(url=f"{base}/{user_id}")


@app.api_route("/store/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def gitea_proxy(path: str, request: Request):
    """Proxy requests to the Gitea UI under the /store path."""
    if not GITEA_URL:
        raise HTTPException(status_code=404, detail="GITEA_URL not configured")

    url = f"{GITEA_URL.rstrip('/')}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()

    def _send():
        return requests.request(
            request.method,
            url,
            params=request.query_params,
            headers=headers,
            data=body,
            allow_redirects=False,
        )

    resp = await asyncio.to_thread(_send)

    response = Response(content=resp.content, status_code=resp.status_code)
    for k, v in resp.headers.items():
        if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}:
            response.headers[k] = v
    return response


@app.get("/store", include_in_schema=False)
async def store_root():
    """Redirect to /store/ for convenience."""
    return RedirectResponse(url="/store/")
