import os
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")


def verify_credentials(username: str, password: str) -> bool:
    return (
        secrets.compare_digest(username, DASHBOARD_USER)
        and secrets.compare_digest(password, DASHBOARD_PASSWORD)
    )


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


def login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)
