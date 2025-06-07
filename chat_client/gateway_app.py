from fastapi import FastAPI
from starlette.responses import RedirectResponse

from auth_app import app as auth_app
from chainlit_app import fastapi_app as chat_app

app = FastAPI(title="Lightning Chat Gateway")

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
