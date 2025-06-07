import os

from fastapi import FastAPI, Request, HTTPException
from starlette.responses import RedirectResponse
from common.jwt_utils import verify_token

from auth_app import app as auth_app
from chainlit_app import fastapi_app as chat_app

app = FastAPI(title="Lightning Chat Gateway")

GITEA_URL = os.environ.get("GITEA_URL")

# Mount the auth and chat applications under separate routes
app.mount("/auth", auth_app)
app.mount("/chat", chat_app)

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to the authentication gateway."""
    return RedirectResponse(url="/auth")

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
