from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import decode_token, parse_uuid
from backend.app.db.models.user import User
from backend.app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = parse_uuid(payload.get("sub", ""))
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


_EMAIL_NOT_VERIFIED_DETAIL = {
    "code": "EMAIL_NOT_VERIFIED",
    "message": "Please verify your email",
}


async def get_verified_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require a verified email for all protected user APIs."""
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_EMAIL_NOT_VERIFIED_DETAIL)
    return user


def raise_if_email_unverified(user: User) -> None:
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_EMAIL_NOT_VERIFIED_DETAIL)
