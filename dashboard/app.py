from fastapi import FastAPI, HTTPException, Depends, Header, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from starlette.requests import Request
import os
import requests

API_BASE = os.environ.get("API_BASE", "http://localhost:7071/api")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")


def _get_token(
    token: str | None = None,
    authorization: str | None = Header(None, alias="Authorization"),
    auth_cookie: str | None = Cookie(None, alias="auth_token"),
):
    """Return bearer token from query param, header, cookie or env."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    if auth_cookie:
        return auth_cookie
    return token or AUTH_TOKEN

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse("tasks.html", {"request": request})


def _api_headers(token: str | None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return headers


@app.get("/tasks.json")
async def list_tasks(token: str = Depends(_get_token)):
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/tasks/{task_id}.json")
async def task_detail(task_id: str, token: str = Depends(_get_token)):
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks/{task_id}", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class EventIn(BaseModel):
    type: str
    metadata: dict


@app.post("/events")
async def create_event(event: EventIn, token: str = Depends(_get_token)):
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "dashboard",
        "type": event.type,
        "metadata": event.metadata,
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{API_BASE}/events", json=payload, headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"status": "queued"}


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    """Render notifications page."""
    return templates.TemplateResponse("notifications.html", {"request": request})


@app.get("/notifications.json")
async def notifications(token: str = Depends(_get_token)):
    """Return recent task notifications."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    tasks = resp.json()
    tasks.sort(key=lambda t: t.get("updated_at", t.get("created_at", "")), reverse=True)
    notifs = [
        {
            "id": t.get("id"),
            "status": t.get("status"),
            "updated_at": t.get("updated_at"),
        }
        for t in tasks[:20]
    ]
    return {"notifications": notifs}


@app.get("/analytics.json")
async def analytics(token: str = Depends(_get_token)):
    """Return basic analytics derived from tasks."""
    headers = _api_headers(token)
    resp = requests.get(f"{API_BASE}/tasks", headers=headers)
    if resp.status_code >= 300:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    tasks = resp.json()
    total = len(tasks)
    status_counts: dict[str, int] = {}
    total_cost = 0.0
    for t in tasks:
        status = t.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        cost = t.get("cost", {}).get("cost")
        if cost is not None:
            try:
                total_cost += float(cost)
            except Exception:
                pass
    return {"total": total, "status": status_counts, "cost": total_cost}

