from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from auth_app import app as auth_app
import sys, os

# Add integrated_app to Python path
integrated_app_path = os.path.join(os.path.dirname(__file__), "integrated_app")
if os.path.exists(integrated_app_path):
    sys.path.insert(0, integrated_app_path)
    from app import app as integrated_ui_app
else:
    # Fallback for development
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "integrated_app"))
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


@app.get("/request-access", include_in_schema=False)
async def request_access_root_get():
    """Backward compatibility for old request access path."""
    return RedirectResponse(url="/auth/request-access")


@app.post("/request-access", include_in_schema=False)
async def request_access_root_post():
    """Redirect POST requests to the authentication service."""
    return RedirectResponse(url="/auth/request-access")


@app.get("/chat", include_in_schema=False)
async def legacy_chat():
    """Backward compatibility for old chat path."""
    return RedirectResponse(url="/app")


@app.get("/waitlist", include_in_schema=False)
async def waitlist_root():
    """Redirect to the authentication waitlist page."""
    return RedirectResponse(url="/auth/waitlist")


@app.get("/health")
async def health():
    return {"status": "ok"}
