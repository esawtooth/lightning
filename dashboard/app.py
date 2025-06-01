from fastapi import FastAPI, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from starlette.requests import Request
import os
import requests

API_BASE = os.environ.get("API_BASE", "http://localhost:7071/api")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")


def _get_token(token: str = None):
    return token or AUTH_TOKEN

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class LoginForm(BaseModel):
    username: str
    password: str


from starlette.requests import Request


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


@app.post("/login")
async def login(form: LoginForm):
    resp = requests.post(f"{API_BASE}/userauth/login", json=form.dict())
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    token = resp.json().get("token")
    response = RedirectResponse("/", status_code=302)
    if token:
        response.set_cookie("token", token, httponly=True)
    return response


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

