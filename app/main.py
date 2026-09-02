import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    SECRET_KEY,
    is_authenticated,
    login_redirect,
    require_auth,
    verify_credentials,
)
from app.database import get_alert, get_alerts, get_stats, init_db, insert_alert, update_alert_status
from app.models import AlertStatus, AlertType
from app.parsers import parse_webhook

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")

TIME_RANGE_OPTIONS = [
    {"value": 30, "label": "Last 30 min"},
    {"value": 60, "label": "Last 1 hour"},
    {"value": 120, "label": "Last 2 hours"},
    {"value": 360, "label": "Last 6 hours"},
    {"value": 720, "label": "Last 12 hours"},
    {"value": 1440, "label": "Last 1 day"},
    {"value": 2880, "label": "Last 2 days"},
    {"value": 4320, "label": "Last 3 days"},
    {"value": 5760, "label": "Last 4 days"},
    {"value": 7200, "label": "Last 5 days"},
    {"value": 8640, "label": "Last 6 days"},
    {"value": 10080, "label": "Last 7 days"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Mon Dashboard", description="Alert monitoring dashboard", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_credentials(username, password):
        request.session["authenticated"] = True
        request.session["username"] = username
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password"})


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authenticated(request):
        return login_redirect()
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/alerts")
async def list_alerts(
    request: Request,
    alert_type: str | None = Query(None),
    status: str | None = Query(None),
    since_minutes: int | None = Query(None, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    require_auth(request)
    alerts = await get_alerts(
        alert_type=alert_type,
        status=status,
        since_minutes=since_minutes,
        limit=limit,
    )
    return {"alerts": [a.model_dump() for a in alerts]}


@app.get("/api/alerts/{alert_id}")
async def fetch_alert(alert_id: int, request: Request):
    require_auth(request)
    alert = await get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump()


@app.get("/api/stats")
async def stats(request: Request, since_minutes: int | None = Query(None, ge=1)):
    require_auth(request)
    return (await get_stats(since_minutes=since_minutes)).model_dump()


@app.patch("/api/alerts/{alert_id}/status")
async def patch_alert_status(alert_id: int, request: Request):
    require_auth(request)
    body = await request.json()
    status_value = body.get("status")
    try:
        status = AlertStatus(status_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid status") from exc

    alert = await update_alert_status(alert_id, status)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump()


def _check_token(token: str | None) -> None:
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="invalid_token")


async def _read_webhook_body(request: Request) -> dict | str:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        return await request.json()

    return (await request.body()).decode("utf-8", errors="replace")


@app.post("/webhook", response_class=PlainTextResponse)
@app.post("/webhook/{token}", response_class=PlainTextResponse)
async def incoming_webhook(request: Request, token: str | None = None):
    _check_token(token)
    body = await _read_webhook_body(request)

    source = request.headers.get("x-alert-source", "webhook")
    if isinstance(body, dict):
        source = body.get("username") or body.get("source") or source

    alert = parse_webhook(body, source=source)
    await insert_alert(alert)
    return "ok"


@app.get("/api/alert-types")
async def alert_types(request: Request):
    require_auth(request)
    return {
        "types": [
            {"id": t.value, "label": t.value.replace("_", " ").title()}
            for t in AlertType
        ],
        "time_ranges": TIME_RANGE_OPTIONS,
    }
