import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import get_alert, get_alerts, get_stats, init_db, insert_alert, update_alert_status
from app.models import AlertStatus, AlertType
from app.parsers import parse_webhook

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Mon Dashboard", description="Alert monitoring dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/alerts")
async def list_alerts(
    alert_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    alerts = await get_alerts(alert_type=alert_type, status=status, limit=limit)
    return {"alerts": [a.model_dump() for a in alerts]}


@app.get("/api/alerts/{alert_id}")
async def fetch_alert(alert_id: int):
    alert = await get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump()


@app.get("/api/stats")
async def stats():
    return (await get_stats()).model_dump()


@app.patch("/api/alerts/{alert_id}/status")
async def patch_alert_status(alert_id: int, request: Request):
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
    """
    Slack-style incoming webhook.

    POST JSON:  {"text": "your alert message"}
    POST text:  plain alert body also works

    Optional: set WEBHOOK_TOKEN env var and use POST /webhook/{token}
    """
    _check_token(token)
    body = await _read_webhook_body(request)

    source = request.headers.get("x-alert-source", "webhook")
    if isinstance(body, dict):
        source = body.get("username") or body.get("source") or source

    alert = parse_webhook(body, source=source)
    await insert_alert(alert)
    return "ok"


@app.get("/api/alert-types")
async def alert_types():
    return {
        "types": [
            {"id": t.value, "label": t.value.replace("_", " ").title()}
            for t in AlertType
        ]
    }
