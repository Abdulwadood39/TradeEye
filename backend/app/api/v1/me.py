from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user
from backend.app.core.limiter import limiter
from backend.app.core.security import verify_password
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.auth import DeleteAccountRequest, MessageResponse, UserResponse
from backend.app.schemas.catalog import UserKpiResponse
from backend.app.services.user_kpi_service import get_user_kpis
from backend.app.services.user_service import UserDeletionError, delete_user_account

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


@router.delete("", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect")

    try:
        await delete_user_account(db, user.id)
        await db.commit()
    except UserDeletionError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return MessageResponse(message="Account deleted successfully.")
