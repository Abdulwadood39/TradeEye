from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.auth import UserResponse
from backend.app.schemas.catalog import UserKpiResponse
from backend.app.services.user_kpi_service import get_user_kpis

router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(get_verified_user)])


@router.get("", response_model=UserResponse)
async def get_profile(user: User = Depends(get_verified_user)) -> UserResponse:
    return UserResponse.from_user(user)


@router.get("/kpis", response_model=UserKpiResponse)
async def get_kpis(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> UserKpiResponse:
    data = await get_user_kpis(db, user)
    return UserKpiResponse(**data)
