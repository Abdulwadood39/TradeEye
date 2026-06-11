from __future__ import annotations

from fastapi import HTTPException, Request, status

from backend.app.core.config import get_settings
from backend.app.core.security import verify_password


def is_admin_authenticated(request: Request) -> bool:
    return request.session.get("admin_authenticated") is True


def require_admin(request: Request) -> None:
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})


def verify_admin_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    if username != settings.admin_username:
        return False
    if not settings.admin_password_hash:
        return False
    return verify_password(password, settings.admin_password_hash)
