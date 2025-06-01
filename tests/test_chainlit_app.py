import os
import sys
import types
import importlib.util
import asyncio


def load_chainlit_app(monkeypatch, capture):
    # Stub chainlit
    cl_mod = types.ModuleType('chainlit')
    handlers = {}

    def on_message(func):
        handlers['handler'] = func
        return func

    def on_chat_start(func):
        return func

    class Msg:
        def __init__(self, content, author='user'):
            self.content = content
            self.author = author
        async def send(self):
            capture.setdefault('sent', []).append(self)

    cl_mod.on_message = on_message
    cl_mod.on_chat_start = on_chat_start
    cl_mod.Message = Msg
    def mount(path, app, **kw):
        pass
    def middleware(typ):
        def wrapper(func):
            return func
        return wrapper
    app_obj = types.SimpleNamespace(
        post=lambda path: (lambda f: f),
        get=lambda path: (lambda f: f),
        mount=mount,
        middleware=middleware,
    )
    cl_mod.server = types.SimpleNamespace(app=app_obj)
    monkeypatch.setitem(sys.modules, 'chainlit', cl_mod)
    monkeypatch.setitem(sys.modules, 'chainlit.server', types.SimpleNamespace(app=app_obj))

    # Stub fastapi
    fastapi_mod = types.ModuleType('fastapi')
    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            self.status_code = status_code
            self.detail = detail
    class FastAPI:
        def mount(self, *a, **kw):
            pass
        def get(self, *a, **kw):
            def wrapper(f):
                return f
            return wrapper
        def post(self, *a, **kw):
            def wrapper(f):
                return f
            return wrapper
    def Depends(obj):
        return obj
    class Jinja2Templates:
        def __init__(self, directory):
            pass
    class RedirectResponse:
        def __init__(self, *a, **kw):
            pass
    class HTMLResponse:
        pass
    class StaticFiles:
        def __init__(self, *a, **kw):
            pass
    fastapi_mod.HTTPException = HTTPException
    fastapi_mod.FastAPI = FastAPI
    fastapi_mod.Depends = Depends
    fastapi_mod.Jinja2Templates = Jinja2Templates
    fastapi_mod.RedirectResponse = RedirectResponse
    fastapi_mod.HTMLResponse = HTMLResponse
    fastapi_mod.StaticFiles = StaticFiles
    templating_mod = types.ModuleType('fastapi.templating')
    templating_mod.Jinja2Templates = Jinja2Templates
    responses_mod = types.ModuleType('fastapi.responses')
    responses_mod.RedirectResponse = RedirectResponse
    responses_mod.HTMLResponse = HTMLResponse
    staticfiles_mod = types.ModuleType('fastapi.staticfiles')
    staticfiles_mod.StaticFiles = StaticFiles
    monkeypatch.setitem(sys.modules, 'fastapi.templating', templating_mod)
    monkeypatch.setitem(sys.modules, 'fastapi.responses', responses_mod)
    monkeypatch.setitem(sys.modules, 'fastapi.staticfiles', staticfiles_mod)
    # Stub dashboard module
    dashboard_mod = types.ModuleType('dashboard')
    dashboard_app_mod = types.ModuleType('dashboard.app')
    dashboard_app_mod.app = types.SimpleNamespace()
    dashboard_mod.app = dashboard_app_mod.app
    monkeypatch.setitem(sys.modules, 'dashboard', dashboard_mod)
    monkeypatch.setitem(sys.modules, 'dashboard.app', dashboard_app_mod)
    # Stub pydantic
    pydantic_mod = types.ModuleType('pydantic')
    class BaseModel:
        pass
    pydantic_mod.BaseModel = BaseModel
    monkeypatch.setitem(sys.modules, 'pydantic', pydantic_mod)
    # Stub starlette
    starlette_mod = types.ModuleType('starlette.requests')
    class Request:
        pass
    starlette_mod.Request = Request
    monkeypatch.setitem(sys.modules, 'starlette.requests', starlette_mod)
    monkeypatch.setitem(sys.modules, 'fastapi', fastapi_mod)

    # Stub requests
    req_mod = types.ModuleType('requests')
    def post(url, json=None, headers=None):
        capture['url'] = url
        capture['json'] = json
        capture['headers'] = headers
        return types.SimpleNamespace(status_code=200, text='')
    req_mod.post = post
    monkeypatch.setitem(sys.modules, 'requests', req_mod)

    # Load module
    spec = importlib.util.spec_from_file_location(
        'chat_client.chainlit_app',
        os.path.join(os.path.dirname(__file__), '..', 'chat_client', 'chainlit_app.py')
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['chat_client.chainlit_app'] = module
    spec.loader.exec_module(module)
    return handlers['handler'], module


async def run_handler(handler, content='hi', author='u'):
    msg = sys.modules['chainlit'].Message(content, author)
    await handler(msg)


def test_authorization_header(monkeypatch):
    monkeypatch.setenv('EVENT_API_URL', 'http://api')
    monkeypatch.setenv('AUTH_TOKEN', 'tok')
    capture = {}
    handler, module = load_chainlit_app(monkeypatch, capture)
    asyncio.run(run_handler(handler))
    assert capture['headers']['Authorization'] == 'Bearer tok'
    assert 'X-User-ID' not in capture['headers']


def test_missing_token(monkeypatch):
    monkeypatch.setenv('EVENT_API_URL', 'http://api')
    monkeypatch.delenv('AUTH_TOKEN', raising=False)
    capture = {}
    handler, module = load_chainlit_app(monkeypatch, capture)
    asyncio.run(run_handler(handler))
    assert capture['sent'][0].content == 'AUTH_TOKEN not configured'


