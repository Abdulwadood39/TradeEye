from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_verified_user
from backend.app.db.models.user import User
from backend.app.schemas.auth import UserResponse

router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(get_verified_user)])


@router.get("", response_model=UserResponse)
async def get_profile(user: User = Depends(get_verified_user)) -> UserResponse:
    return UserResponse.from_user(user)
