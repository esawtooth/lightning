from fastapi import FastAPI
from starlette.responses import RedirectResponse

from auth_app import app as auth_app
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'integrated_app'))
from app import app as integrated_ui_app

app = FastAPI(title="Vextir Chat Gateway")

# Mount the auth and chat applications under separate routes
app.mount("/auth", auth_app)
app.mount("/app", integrated_ui_app)

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to the authentication gateway."""
    return RedirectResponse(url="/auth")


@app.get("/register", include_in_schema=False)
async def register_root():
    """Legacy registration path for convenience."""
    return RedirectResponse(url="/auth/register")


@app.get("/chat", include_in_schema=False)
async def legacy_chat():
    """Backward compatibility for old chat path."""
    return RedirectResponse(url="/app")

@app.get("/health")
async def health():
    return {"status": "ok"}


